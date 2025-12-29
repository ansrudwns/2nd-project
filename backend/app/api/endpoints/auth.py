from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.tables import User
from app.schemas.user import UserCreate, UserResponse, EmailCheck
from app.core.security import get_password_hash, verify_password, create_access_token
from datetime import datetime
from typing import Annotated

router = APIRouter()

# Update tokenUrl to match the actual login route
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
    from jose import JWTError, jwt
    from app.core.security import SECRET_KEY, ALGORITHM
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

@router.post("/signup", response_model=UserResponse)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password and create user
    hashed_password = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.delete("/me", status_code=204)
def delete_user_me(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Hard Delete
    # Note: If analysis_history has foreign key constraint without CASCADE, we might need to delete history first manually.
    # Assuming CASCADE or manual deletion. Let's try manual first to be safe.
    try:
        from app.models.tables import Analysis, AuditLog
        
        # 1. Find user's analyses
        user_analyses = db.query(Analysis).filter(Analysis.user_id == current_user.id).all()
        analysis_ids = [a.id for a in user_analyses]
        
        if analysis_ids:
            # 2. Delete related AuditLogs first (if any exist)
            db.query(AuditLog).filter(AuditLog.analysis_id.in_(analysis_ids)).delete(synchronize_session=False)
            
            # 3. Delete Analyses
            db.query(Analysis).filter(Analysis.user_id == current_user.id).delete(synchronize_session=False)
            
        # 4. Delete User
        db.delete(current_user)
        db.commit()
        return
    except Exception as e:
        db.rollback()
        # Log the full error for better debugging if it happens again
        print(f"Delete Account Error: {e}") 
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

@router.post("/check-email")
def check_email(email_check: EmailCheck, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == email_check.email).first()
    if db_user:
        return {"exists": True, "message": "Email already registered"}
    return {"exists": False, "message": "Email available"}

@router.post("/login")
def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Session = Depends(get_db)):
    # Verify user
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create token
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}
