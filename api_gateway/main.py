from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import httpx
import jwt
import redis
import json
import time
import uuid
from typing import Optional
import os
from datetime import datetime, timedelta
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Vet Clinic API Gateway", version="1.0.0")

# Configuración
SERVICES = {
    "auth": "http://auth-service:8001",
    "clients": "http://clients-pets-service:8002", 
    "appointments": "http://appointments-service:8003",
    "medical": "http://medical-records-service:8004",
    "billing": "http://billing-service:8005",
    "notifications": "http://notifications-service:8006",
    "employees": "http://employees-service:8007",
}

# Redis para caché y rate limiting
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Rate Limiting
class RateLimiter:
    def __init__(self, redis_client, max_requests: int = 100, window: int = 3600):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window = window
    
    async def is_allowed(self, identifier: str) -> bool:
        """Verificar si la solicitud está dentro del límite de rate"""
        key = f"rate_limit:{identifier}"
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, self.window)
        result = pipe.execute()
        
        current_requests = result[0]
        return current_requests <= self.max_requests

rate_limiter = RateLimiter(redis_client)

# Autenticación
async def verify_token(request: Request):
    """Verificar token JWT"""
    token = request.headers.get("Authorization")
    if not token:
        return None
    
    try:
        # Remover 'Bearer ' del token
        token = token.replace("Bearer ", "")
        
        # Verificar en caché
        cached_user = redis_client.get(f"token:{token}")
        if cached_user:
            return json.loads(cached_user)
        
        # Verificar con el servicio de autenticación
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SERVICES['auth']}/verify-token",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                user_data = response.json()
                # Cachear por 10 minutos
                redis_client.setex(f"token:{token}", 600, json.dumps(user_data))
                return user_data
            
    except Exception as e:
        logger.error(f"Error verificando token: {e}")
    
    return None

async def get_current_user(request: Request):
    """Dependency para obtener el usuario actual"""
    user = await verify_token(request)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return user

# Health Check
@app.get("/health")
async def health_check():
    """Verificar estado de la API Gateway"""
    services_health = {}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICES.items():
            try:
                response = await client.get(f"{url}/health")
                services_health[name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response.elapsed.total_seconds(),
                    "status_code": response.status_code
                }
            except Exception as e:
                services_health[name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
    
    all_healthy = all(s["status"] == "healthy" for s in services_health.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "services": services_health
    }

# Middleware para logging y rate limiting
@app.middleware("http")
async def logging_and_rate_limit_middleware(request: Request, call_next):
    # Rate limiting
    client_ip = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    identifier = f"{client_ip}:{user_agent}"
    
    if not await rate_limiter.is_allowed(identifier):
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"}
        )
    
    # Logging
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # Añadir ID de request para tracking
    request.state.request_id = request_id
    
    logger.info(f"Request {request_id}: {request.method} {request.url} from {client_ip}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    logger.info(f"Request {request_id} completed in {process_time:.3f}s with status {response.status_code}")
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    return response

# Proxy requests to services
async def proxy_request(service_name: str, path: str, request: Request):
    """Hacer proxy de request a un microservicio"""
    if service_name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
    
    service_url = SERVICES[service_name]
    target_url = f"{service_url}{path}"
    
    # Preparar headers
    headers = dict(request.headers)
    headers["X-Request-ID"] = request.state.request_id
    headers["X-Forwarded-For"] = request.client.host
    
    # Preparar body si existe
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        body = await request.body()
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=request.query_params,
                content=body,
                follow_redirects=True
            )
            
            # Crear response con el mismo status code y headers
            response_headers = dict(response.headers)
            # Remover headers que pueden causar problemas
            response_headers.pop('content-encoding', None)
            response_headers.pop('transfer-encoding', None)
            
            return JSONResponse(
                content=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
                status_code=response.status_code,
                headers=response_headers
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Timeout calling {service_name}")
    except httpx.RequestError as e:
        logger.error(f"Error calling {service_name}: {e}")
        raise HTTPException(status_code=503, detail=f"Service {service_name} unavailable")

# Routes de autenticación (sin auth requerida)
@app.post("/auth/login")
async def login(request: Request):
    return await proxy_request("auth", "/login", request)

@app.post("/auth/register")
async def register(request: Request):
    return await proxy_request("auth", "/register", request)

@app.post("/auth/refresh")
async def refresh_token(request: Request):
    return await proxy_request("auth", "/refresh", request)

@app.post("/auth/forgot-password")
async def forgot_password(request: Request):
    return await proxy_request("auth", "/forgot-password", request)

# Routes protegidas - Clientes y Mascotas
@app.api_route("/clients/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def clients_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("clients", f"/{path}", request)

# Routes protegidas - Citas
@app.api_route("/appointments/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def appointments_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("appointments", f"/{path}", request)

# Routes protegidas - Historia Clínica
@app.api_route("/medical/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def medical_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("medical", f"/{path}", request)

# Routes protegidas - Facturación
@app.api_route("/billing/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def billing_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("billing", f"/{path}", request)

# Routes protegidas - Notificaciones
@app.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def notifications_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("notifications", f"/{path}", request)

# Routes protegidas - Empleados
@app.api_route("/employees/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def employees_proxy(path: str, request: Request, user=Depends(get_current_user)):
    return await proxy_request("employees", f"/{path}", request)

# Endpoint especial para obtener información combinada
@app.get("/dashboard/summary")
async def dashboard_summary(request: Request, user=Depends(get_current_user)):
    """Obtener resumen del dashboard combinando información de varios servicios"""
    summary = {}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Hacer requests paralelos a varios servicios
        try:
            # Obtener citas de hoy
            appointments_response = await client.get(
                f"{SERVICES['appointments']}/today",
                headers={"Authorization": request.headers.get("Authorization")}
            )
            if appointments_response.status_code == 200:
                summary["todays_appointments"] = appointments_response.json()
            
            # Obtener facturas pendientes
            billing_response = await client.get(
                f"{SERVICES['billing']}/pending",
                headers={"Authorization": request.headers.get("Authorization")}
            )
            if billing_response.status_code == 200:
                summary["pending_invoices"] = billing_response.json()
            
            # Obtener notificaciones pendientes
            notifications_response = await client.get(
                f"{SERVICES['notifications']}/pending",
                headers={"Authorization": request.headers.get("Authorization")}
            )
            if notifications_response.status_code == 200:
                summary["pending_notifications"] = notifications_response.json()
            
        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}")
            summary["error"] = "Error fetching some dashboard data"
    
    return summary

# WebSocket support para notificaciones en tiempo real
from fastapi import WebSocket, WebSocketDisconnect
from typing import List

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remover conexiones cerradas
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket)
    try:
        while True:
            # Mantener conexión viva
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)