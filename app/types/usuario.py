

# Properties to receive via API on update
class UsuarioUpdate(UsuarioBase):
    email: Optional[EmailStr] = None

# Properties to return via API
class Usuario(UsuarioInDBBase):
    pass


# Properties stored in DB
class UsuarioInDB(UsuarioInDBBase):
    pass 