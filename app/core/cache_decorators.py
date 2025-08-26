"""
Decoradores para cachear funciones automáticamente
"""
import functools
import hashlib
import json
from typing import Callable, Protocol, ParamSpec, TypeVar, cast
from app.core.cache_manager import cache_manager
import logging

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R", covariant=True)

class CacheableFunction(Protocol[P, R]):
    """Protocol para funciones con soporte de caché e invalidación"""
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def invalidate_cache(self, *args: P.args, **kwargs: P.kwargs) -> None: ...

def cached(
    namespace: str,
    ttl: int | None = None,
    key_func: Callable[..., str] | None = None,
) -> Callable[[Callable[P, R]], CacheableFunction[P, R]]:
    """
    Decorador para cachear resultados de funciones
    
    Args:
        namespace: Categoría del cache (ml_features, notification_rules, etc.)
        ttl: Time to live en segundos
        key_func: Función personalizada para generar la clave de cache
    """
    def decorator(func: Callable[P, R]) -> CacheableFunction[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Generar clave de cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Generar clave automática basada en argumentos
                key_data = {
                    'func': func.__name__,
                    'args': args,
                    'kwargs': kwargs
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
        
        # Agregar método para invalidar cache
        def invalidate_cache(*args: P.args, **kwargs: P.kwargs) -> None:
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                key_data = {
                    'func': func.__name__,
                    'args': args,
                    'kwargs': kwargs
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

def cache_ml_features(ttl: int = 3600) -> Callable[[Callable[P, R]], CacheableFunction[P, R]]:
    """Decorador específico para features ML"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = kwargs.get('business_id') or (args[0] if args else 'unknown')
        return f"features_{business_id}"
    
    return cached('ml_features', ttl, key_func)

def cache_ml_predictions(ttl: int = 1800) -> Callable[[Callable[P, R]], CacheableFunction[P, R]]:  # 30 minutos
    """Decorador específico para predicciones ML"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = kwargs.get('business_id') or (args[0] if args else 'unknown')
        prediction_type = kwargs.get('prediction_type') or (args[1] if len(args) > 1 else 'default')
        return f"prediction_{business_id}_{prediction_type}"
    
    return cached('ml_predictions', ttl, key_func)

def cache_notification_rules(ttl: int = 600) -> Callable[[Callable[P, R]], CacheableFunction[P, R]]:  # 10 minutos
    """Decorador específico para reglas de notificación"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = kwargs.get('business_id') or (args[0] if args else 'unknown')
        return f"rules_{business_id}"
    
    return cached('notification_rules', ttl, key_func)

def cache_business_config(ttl: int = 1800) -> Callable[[Callable[P, R]], CacheableFunction[P, R]]:  # 30 minutos
    """Decorador específico para configuración de negocio"""
    def key_func(*args: object, **kwargs: object) -> str:
        business_id = kwargs.get('business_id') or (args[0] if args else 'unknown')
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
                # Usar business_id por defecto
                business_id = kwargs.get('business_id') or (args[0] if args else None)
                if business_id:
                    cache_key = str(business_id)
                    cache_manager.delete(cache_namespace, cache_key)
                    logger.info(f"Cache invalidated after update: {cache_namespace}:{cache_key}")
            
            return result
        
        return wrapper
    
    return decorator
