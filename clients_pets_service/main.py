from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import redis
import json
import uuid
import secrets
from typing import Optional
from sqlalchemy import create_engine, Column, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel, EmailStr, validator
import re
import logging

# Configuración
app = FastAPI(title="Auth Service", version="1.0.0")
security = HTTPBearer()

# Configuración de seguridad
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Redis para tokens
redis_client = redis.Redis(host='redis', port=6379, db=1, decode_responses=True)

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos de base de datos
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(15))
    user_type = Column(String(20), default='client')  # client, employee, admin
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime)
    last_login = Column(DateTime)
    failed_login_attempts = Column(String(10), default='0')
    locked_until = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Crear tablas
Base.metadata.create_all(bind=engine)

# Dependency para obtener sesión de DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modelos Pydantic
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    user_type: str = 'client'
    
    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username debe tener al menos 3 caracteres')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username solo puede contener letras, números y guiones bajos')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v
    
    @validator('phone')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[1-9]\d{9,14}$', v.replace(' ', '').replace('-', '')):
            raise ValueError('Formato de teléfono inválido')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    user_type: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'[a-z]', v):
            raise ValueError('La contraseña debe contener al menos una minúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        return v

# Funciones auxiliares
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash de contraseña"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Crear JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(user_id: str, db: Session) -> str:
    """Crear refresh token"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Desactivar tokens anteriores
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.is_active == True
    ).update({RefreshToken.is_active: False})
    
    # Crear nuevo token
    db_token = RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )
    db.add(db_token)
    db.commit()
    
    return token

def verify_token(token: str) -> Optional[dict]:
    """Verificar JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if user_id is None or token_type != "access":
            return None
        
        return {"user_id": user_id, "exp": payload.get("exp")}
    except JWTError:
        return None

def is_account_locked(user: User) -> bool:
    """Verificar si la cuenta está bloqueada"""
    if user.locked_until and user.locked_until > datetime.utcnow():
        return True
    return False

def increment_failed_attempts(user: User, db: Session):
    """Incrementar intentos fallidos de login"""
    try:
        current_attempts = int(user.failed_login_attempts or '0')
    except:
        current_attempts = 0
    
    current_attempts += 1
    user.failed_login_attempts = str(current_attempts)
    
    # Bloquear cuenta después de 5 intentos fallidos
    if current_attempts >= 5:
        user.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    db.commit()

def reset_failed_attempts(user: User, db: Session):
    """Resetear intentos fallidos de login"""
    user.failed_login_attempts = '0'
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.commit()

# Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "auth"}

@app.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registrar nuevo usuario"""
    # Verificar si el usuario ya existe
    existing_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Username o email ya existe"
        )
    
    # Crear nuevo usuario
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        password_hash=hashed_password,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        user_type=user.user_type
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # TODO: Enviar email de verificación
    
    return UserResponse.from_orm(db_user)

@app.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Iniciar sesión"""
    # Buscar usuario
    user = db.query(User).filter(
        (User.username == user_credentials.username) | 
        (User.email == user_credentials.username)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas"
        )
    
    # Verificar si la cuenta está activa
    if not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Cuenta desactivada"
        )
    
    # Verificar si la cuenta está bloqueada
    if is_account_locked(user):
        raise HTTPException(
            status_code=401,
            detail="Cuenta bloqueada temporalmente. Intenta más tarde."
        )
    
    # Verificar contraseña
    if not verify_password(user_credentials.password, user.password_hash):
        increment_failed_attempts(user, db)
        raise HTTPException(
            status_code=401,
            detail="Credenciales incorrectas"
        )
    
    # Login exitoso
    reset_failed_attempts(user, db)
    
    # Crear tokens
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "user_type": user.user_type},
        expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(str(user.id), db)
    
    # Cachear token en Redis
    redis_client.setex(
        f"token:{access_token}",
        ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        json.dumps({
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "user_type": user.user_type,
            "token": access_token
        })
    )
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@app.post("/refresh", response_model=Token)
async def refresh_token_endpoint(token_data: TokenRefresh, db: Session = Depends(get_db)):
    """Renovar access token usando refresh token"""
    # Verificar refresh token
    refresh_token = db.query(RefreshToken).filter(
        RefreshToken.token == token_data.refresh_token,
        RefreshToken.is_active == True,
        RefreshToken.expires_at > datetime.utcnow()
    ).first()
    
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token inválido o expirado"
        )
    
    # Obtener usuario
    user = db.query(User).filter(User.id == refresh_token.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Usuario no válido"
        )
    
    # Crear nuevo access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "user_type": user.user_type},
        expires_delta=access_token_expires
    )
    
    # Cachear token en Redis
    redis_client.setex(
        f"token:{access_token}",
        ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        json.dumps({
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "user_type": user.user_type,
            "token": access_token
        })
    )
    
    return Token(
        access_token=access_token,
        refresh_token=token_data.refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@app.get("/verify-token")
async def verify_token_endpoint(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verificar validez del token"""
    token = credentials.credentials
    
    # Verificar en Redis primero
    cached_user = redis_client.get(f"token:{token}")
    if cached_user:
        return json.loads(cached_user)
    
    # Verificar token JWT
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token inválido"
        )
    
    # Token válido pero no en caché, regenerar caché
    # Esto podría pasar si Redis se reinició
    user_id = payload["user_id"]
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=401,
                detail="Usuario no válido"
            )
        
        user_data = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "user_type": user.user_type,
            "token": token
        }
        
        # Cachear por tiempo restante del token
        exp_timestamp = payload["exp"]
        remaining_time = exp_timestamp - datetime.utcnow().timestamp()
        if remaining_time > 0:
            redis_client.setex(f"token:{token}", int(remaining_time), json.dumps(user_data))
        
        return user_data

@app.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """Cerrar sesión"""
    token = credentials.credentials
    
    # Remover token de Redis
    redis_client.delete(f"token:{token}")
    
    # Invalidar refresh tokens asociados
    payload = verify_token(token)
    if payload:
        user_id = payload["user_id"]
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active == True
        ).update({RefreshToken.is_active: False})
        db.commit()
    
    return {"message": "Logout exitoso"}

@app.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Solicitar reset de contraseña"""
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        # No revelar si el email existe o no por seguridad
        return {"message": "Si el email existe, se enviará un enlace de recuperación"}
    
    # Invalidar tokens anteriores
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.is_used == False
    ).update({PasswordResetToken.is_used: True})
    
    # Crear nuevo token
    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    
    db_token = PasswordResetToken(
        user_id=user.id,
        token=reset_token,
        expires_at=expires_at
    )
    db.add(db_token)
    db.commit()
    
    # TODO: Enviar email con enlace de reset
    
    return {"message": "Si el email existe, se enviará un enlace de recuperación"}

@app.post("/reset-password")
async def reset_password(request: PasswordReset, db: Session = Depends(get_db)):
    """Resetear contraseña con token"""
    # Verificar token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == request.token,
        PasswordResetToken.is_used == False,
        PasswordResetToken.expires_at > datetime.utcnow()
    ).first()
    
    if not reset_token:
        raise HTTPException(
            status_code=400,
            detail="Token de reset inválido o expirado"
        )
    
    # Obtener usuario
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Usuario no encontrado"
        )
    
    # Actualizar contraseña
    user.password_hash = get_password_hash(request.new_password)
    reset_token.is_used = True
    
    # Invalidar todos los refresh tokens
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id
    ).update({RefreshToken.is_active: False})
    
    db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}

@app.put("/change-password")
async def change_password(
    request: PasswordChange,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Cambiar contraseña (usuario autenticado)"""
    # Verificar token
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    # Obtener usuario
    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Verificar contraseña actual
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Contraseña actual incorrecta"
        )
    
    # Actualizar contraseña
    user.password_hash = get_password_hash(request.new_password)
    db.commit()
    
    return {"message": "Contraseña cambiada exitosamente"}

@app.get("/profile", response_model=UserResponse)
async def get_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Obtener perfil del usuario autenticado"""
    # Verificar token
    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    # Obtener usuario
    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return UserResponse.from_orm(user)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)