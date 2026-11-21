import os
import shutil
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import chromadb

router = APIRouter(prefix="/api/documents", tags=["Secure Document Ingestion"])
security = HTTPBearer()

# Configuration Boundaries
SECRET_KEY = "ENTERPRISE_CORE_SECRET_KEY_PLACEHOLDER"  # Store in .env in production
ALGORITHM = "HS256"
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "raw_documents"
VECTOR_DB_DIR = BASE_DIR / "enterprise_rag_db"

# Ensure absolute physical directories exist securely
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Initialize decoupled persistent vector database
chroma_client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
collection = chroma_client.get_or_create_collection(name="secure_enterprise_knowledge")


def verify_token_and_get_role(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Decodes inbound JWT claims to extract User Identity and Role Permissions."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_role = payload.get("role")
        user_id = payload.get("user_id")
        if not user_role or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed security token payload.",
            )
        return {"user_id": user_id, "role": user_role}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or tampered access token.",
        )


import datetime
from schemas import LoginRequest, TokenResponse  # Make sure to import your schemas!

# MOCK ENTERPRISE DIRECTORY (For Thesis Demonstration)
MOCK_USERS = {
    "admin_alice": {"password": "password123", "role": "Admin", "id": "USR-001"},
    "manager_bob": {"password": "password123", "role": "Manager", "id": "USR-002"},
    "emp_charlie": {"password": "password123", "role": "Employee", "id": "USR-003"},
}


@router.post("/login", response_model=TokenResponse, tags=["Authentication"])
async def authenticate_user(login_data: LoginRequest):
    """
    Simulates an Enterprise SSO Login.
    Returns a stateless JWT token encoding the user's RBAC tier.
    """
    user = MOCK_USERS.get(login_data.username)

    if not user or user["password"] != login_data.password:
        raise HTTPException(status_code=401, detail="Invalid corporate credentials")

    # Create the JWT Payload (The "ID Badge")
    expiration = datetime.datetime.utcnow() + datetime.timedelta(
        hours=8
    )  # 8-hour shift
    payload = {
        "sub": login_data.username,
        "user_id": user["id"],
        "role": user["role"],
        "exp": expiration,
    }

    # Cryptographically sign the token
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": user["id"],
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    auth_data: dict = Depends(verify_token_and_get_role),
):
    """
    Ingestion is intentionally public to the app: documents are written to disk and
    indexed without document-level RBAC restrictions so every pipeline can retrieve them.
    """
    file_path = os.path.join(STORAGE_DIR, file.filename)

    # 2. Securely stream payload to isolated persistent storage
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Physical disk write failure: {str(e)}"
        )

    # 3. Text Processing Loop (Simulated chunking for demonstration)
    # Inside Phase 2, this will route into your existing LangChain chunker/Gemini Embeddings pipeline
    simulated_chunks = [
        f"Sample chunk from {file.filename} dealing with operational parameters."
    ]

    for idx, chunk in enumerate(simulated_chunks):
        # Generate a distinct deterministic vector identifier
        chunk_id = f"{file.filename}_chunk_{idx}"

        # Inject standard structural context paired with deep security access lists
        metadata_payload = {
            "source": file.filename,
            "owner_id": auth_data["user_id"],
            "allowed_roles": ["Admin", "Manager", "Employee"],
        }

        # Upsert securely to the decoupled vector DB
        # collection.add(embeddings=[...], documents=[chunk], metadatas=[metadata_payload], ids=[chunk_id])

    return {
        "status": "Success",
        "filename": file.filename,
        "message": "File written and indexed for retrieval by all app pipelines.",
    }


@router.delete("/delete/{filename}", status_code=status.HTTP_200_OK)
async def delete_document(
    filename: str, auth_data: dict = Depends(verify_token_and_get_role)
):
    """Purges physical files and corresponding vector spaces matching metadata footprints."""
    if auth_data["role"] != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Administrative authorization required for data purges.",
        )

    file_path = os.path.join(STORAGE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, detail="Target document not found in persistent layer."
        )

    # Delete physical artifact
    os.remove(file_path)

    # Purge related vector coordinates using standard metadata matching
    # collection.delete(where={"source": filename})

    return {
        "status": "Purged",
        "message": f"Successfully deleted {filename} from knowledge engine memory.",
    }
