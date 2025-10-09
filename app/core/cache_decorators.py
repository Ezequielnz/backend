"""
Decoradores para cachear funciones automáticamente
"""
import functools
import hashlib
import inspect
import json
from typing import Callable, Protocol, ParamSpec, TypeVar, cast
from app.core.cache_manager import cache_manager
import logging

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R", covariant=True)

def _is_bound_celery_task(args: tuple[object, ...]) -> bool:
    """Detecta si la función decorada es una tarea de Celery con bind=True (self como primer arg)."""
    if not args:
        return False
    first = args[0]
    # Heurística liviana: las tareas de Celery tienen atributos 'request' y 'name'
    return hasattr(first, "request") and hasattr(first, "name")

def _extract_param(
    args: tuple[object, ...],
    kwargs: dict[str, object],
    name: str,
    pos_unbound: int = 0,
    pos_bound: int = 1,
) -> object:
    """Obtiene un parámetro por nombre o posición, considerando si la función está ligada (Celery bind=True)."""
    if name in kwargs:
        return kwargs[name]
    if args:
        index = pos_bound if _is_bound_celery_task(args) else pos_unbound
        if len(args) > index:
            return args[index]
    return "unknown"

class CacheableFunction(Protocol[P, R]):
    """Protocol para funciones con soporte de caché e invalidación"""
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def invalidate_cache(self, *args: P.args, **kwargs: P.kwargs) -> None: ...

def cached(
    namespace: str,
    ttl: int | None = None,
    key_func: Callable[..., str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorador para cachear resultados de funciones
    
    Args:
        namespace: Categoría del cache (ml_features, notification_rules, etc.)
        ttl: Time to live en segundos
        key_func: Función personalizada para generar la clave de cache
    """
    def decorator(func: Callable[P, R]) -> CacheableFunction[P, R]:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                # Generar clave de cache
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    # Generar clave automática basada en argumentos (tipado explícito)
                    key_data: dict[str, object] = {
                        'func': func.__name__,
                        'args': cast(tuple[object, ...], args),
                        'kwargs': cast(dict[str, object], dict(kwargs)),
                    }
                    key_str = json.dumps(key_data, sort_keys=True, default=str)
                    cache_key = hashlib.md5(key_str.encode()).hexdigest()

                # Intentar obtener del cache
                cached_result = cache_manager.get(namespace, cache_key, ttl)
                if cached_result is not None:
                    logger.debug(f"Cache hit para {func.__name__}: {cache_key}")
                    return cast(R, cached_result)

                # Ejecutar función y cachear resultado
                result: R = await func(*args, **kwargs)
                if result is not None:
                    cache_manager.set(namespace, cache_key, result, ttl)
                    logger.debug(f"Cache set para {func.__name__}: {cache_key}")

                return result
            wrapper = async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                # Generar clave de cache
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    # Generar clave automática basada en argumentos (tipado explícito)
                    key_data: dict[str, object] = {
                        'func': func.__name__,
                        'args': cast(tuple[object, ...], args),
                        'kwargs': cast(dict[str, object], dict(kwargs)),
                    }
                    key_str = json.dumps(key_data, sort_keys=True, default=str)
                    cache_key = hashlib.md5(key_str.encode()).hexdigest()

                # Intentar obtener del cache
                cached_result = cache_manager.get(namespace, cache_key, ttl)
                if cached_result is not None:
                    logger.debug(f"Cache hit para {func.__name__}: {cache_key}")
                    return cast(R, cached_result)

                # Ejecutar función y cachear resultado
                result: R = func(*args, **kwargs)
                if result is not None:
                    cache_manager.set(namespace, cache_key, result, ttl)
                    logger.debug(f"Cache set para {func.__name__}: {cache_key}")

                return result
            wrapper = sync_wrapper
        
        # Agregar método para invalidar cache
        def invalidate_cache(*args: P.args, **kwargs: P.kwargs) -> None:
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_data: dict[str, object] = {
                    'func': func.__name__,
                    'args': cast(tuple[object, ...], args),
                    'kwargs': cast(dict[str, object], dict(kwargs)),
                }
                key_str = json.dumps(key_data, sort_keys=True, default=str)
                cache_key = hashlib.md5(key_str.encode()).hexdigest()
            
            cache_manager.delete(namespace, cache_key)
            logger.info(f"Cache invalidated para {func.__name__}: {cache_key}")
        
        # Adjuntar atributo con cast doble para el type checker (func -> object -> Protocol)
        typed_wrapper = cast(CacheableFunction[P, R], cast(object, wrapper))
        typed_wrapper.invalidate_cache = invalidate_cache
        return typed_wrapper
    
    return decorator

def cache_ml_features(ttl: int = 3600) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorador específico para features ML"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = _extract_param(args, kwargs, 'business_id', 0, 1)
        return f"features_{business_id}"
    
    return cached('ml_features', ttl, key_func)

def cache_ml_predictions(ttl: int = 1800) -> Callable[[Callable[P, R]], Callable[P, R]]:  # 30 minutos
    """Decorador específico para predicciones ML"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = _extract_param(args, kwargs, 'business_id', 0, 1)
        prediction_type = _extract_param(args, kwargs, 'prediction_type', 1, 2) or 'default'
        return f"prediction_{business_id}_{prediction_type}"
    
    return cached('ml_predictions', ttl, key_func)

def cache_notification_rules(ttl: int = 600) -> Callable[[Callable[P, R]], Callable[P, R]]:  # 10 minutos
    """Decorador específico para reglas de notificación"""
    def key_func(*args: object, **kwargs: object) -> str:
        # For NotificationConfigService.get_effective_rules(self, tenant_id: str)
        # args[0] is self, args[1] is tenant_id
        tenant_id = args[1] if len(args) > 1 else "unknown"
        return f"rules_{tenant_id}"

    return cached('notification_rules', ttl, key_func)

def cache_business_config(ttl: int = 1800) -> Callable[[Callable[P, R]], Callable[P, R]]:  # 30 minutos
    """Decorador específico para configuración de negocio"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = _extract_param(args, kwargs, 'business_id', 0, 1)
        return f"config_{business_id}"
    
    return cached('business_config', ttl, key_func)

P2 = ParamSpec("P2")
R2 = TypeVar("R2")

def invalidate_on_update(
    cache_namespace: str,
    key_func: Callable[..., str] | None = None,
) -> Callable[[Callable[P2, R2]], Callable[P2, R2]]:
    """
    Decorador para invalidar cache automáticamente después de updates
    """
    def decorator(func: Callable[P2, R2]) -> Callable[P2, R2]:
        @functools.wraps(func)
        def wrapper(*args: P2.args, **kwargs: P2.kwargs) -> R2:
            # Ejecutar función original
            result: R2 = func(*args, **kwargs)
            
            # Invalidar cache después del update
            if key_func:
                cache_key = key_func(*args, **kwargs)
                cache_manager.delete(cache_namespace, cache_key)
                logger.info(f"Cache invalidated after update: {cache_namespace}:{cache_key}")
            else:
                # Invalidación por defecto basada en namespace
                business_id = _extract_param(args, kwargs, 'business_id', 0, 1)
                if business_id and business_id != "unknown":
                    bid = str(business_id)
                    if cache_namespace == 'ml_features':
                        # Invalidate all feature keys for this tenant (prefix-based)
                        cache_manager.invalidate_pattern(f"{cache_namespace}:features_{bid}")
                        logger.info(f"Cache invalidated after update (pattern): {cache_namespace}:features_{bid}*")
                    elif cache_namespace == 'ml_predictions':
                        prediction_type = _extract_param(args, kwargs, 'prediction_type', 1, 2)
                        if prediction_type and prediction_type != "unknown":
                            cache_key = f"prediction_{bid}_{prediction_type}"
                            cache_manager.delete(cache_namespace, cache_key)
                            logger.info(f"Cache invalidated after update: {cache_namespace}:{cache_key}")
                        else:
                            # Invalidar todas las predicciones para el negocio si no se especifica tipo
                            cache_manager.invalidate_pattern(f"{cache_namespace}:prediction_{bid}_")
                            logger.info(f"Cache invalidated after update (pattern): {cache_namespace}:prediction_{bid}_*")
                    elif cache_namespace == 'notification_rules':
                        cache_key = f"rules_{bid}"
                        cache_manager.delete(cache_namespace, cache_key)
                        logger.info(f"Cache invalidated after update: {cache_namespace}:{cache_key}")
                    elif cache_namespace == 'business_config':
                        cache_key = f"config_{bid}"
                        cache_manager.delete(cache_namespace, cache_key)
                        logger.info(f"Cache invalidated after update: {cache_namespace}:{cache_key}")
                    else:
                        # Fallback: invalidar por business_id simple
                        cache_manager.delete(cache_namespace, bid)
                        logger.info(f"Cache invalidated after update: {cache_namespace}:{bid}")
            
            return result
        
        return wrapper
    
    return decorator
