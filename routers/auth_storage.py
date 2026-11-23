import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

router = APIRouter(prefix="/api/documents", tags=["Secure Document Ingestion"])
security = HTTPBearer()

# Configuration Boundaries
SECRET_KEY = "ENTERPRISE_CORE_SECRET_KEY_PLACEHOLDER"  # Store in .env in production
ALGORITHM = "HS256"
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "raw_documents"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


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
def upload_document(
    request: Request,
    file: UploadFile = File(...),
    auth_data: dict = Depends(verify_token_and_get_role),
):
    """Store and index the uploaded document before reporting success."""
    filename = file.filename
    if not filename or Path(filename).name != filename or any(
        character in filename for character in "/\\:"
    ):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX files are supported.")

    try:
        with TemporaryDirectory(dir=STORAGE_DIR) as directory:
            staged = Path(directory) / f"upload{suffix}"
            with staged.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            request.app.state.index_document(
                staged, filename, auth_data["user_id"], STORAGE_DIR / filename
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Could not extract document text.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Document indexing failed.") from exc

    return {
        "status": "Success",
        "filename": filename,
        "message": "File written and indexed for retrieval by all app pipelines.",
    }


@router.delete("/delete/{filename}", status_code=status.HTTP_200_OK)
def delete_document(
    filename: str, request: Request, auth_data: dict = Depends(verify_token_and_get_role)
):
    """Purges physical files and corresponding vector spaces matching metadata footprints."""
    if auth_data["role"] != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Administrative authorization required for data purges.",
        )

    if Path(filename).name != filename or any(character in filename for character in "/\\:"):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = STORAGE_DIR / filename
    if not file_path.is_file():
        raise HTTPException(
            status_code=404, detail="Target document not found in persistent layer."
        )

    request.app.state.delete_indexed_document(file_path)

    return {
        "status": "Purged",
        "message": f"Successfully deleted {filename} from knowledge engine memory.",
    }
