import os
import jwt
import requests
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Depends, status
from sqlalchemy.orm import Session
from database import get_db, User, Organization

CLERK_JWKS_URL = "https://light-drake-0.clerk.accounts.dev/.well-known/jwks.json"

# In-memory cache for JWKS to avoid fetching on every request
_jwks_cache = None

def get_jwks() -> Dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is None:
        try:
            resp = requests.get(CLERK_JWKS_URL, timeout=5)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            print("[AUTH] Successfully fetched and cached Clerk JWKS.")
        except Exception as e:
            print(f"[AUTH] Failed to fetch JWKS from Clerk: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication server unavailable"
            )
    return _jwks_cache

def verify_token(token: str) -> Dict[str, Any]:
    jwks = get_jwks()
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )
        
    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing kid header"
        )
        
    # Find the key in JWKS
    key_data = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            key_data = key
            break
            
    if not key_data:
        # Force refresh JWKS cache and try again
        global _jwks_cache
        _jwks_cache = None
        jwks = get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                key_data = key
                break
                
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token key ID"
        )
        
    try:
        # Construct public key using PyJWT's RSA decoding algorithm
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        # Decode and verify token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature verification failed"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )

def get_current_user(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_firstname: Optional[str] = Header(None),
    x_user_lastname: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )
        
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user ID claim (sub)"
        )
        
    clerk_org_id = payload.get("org_id")
    org_role = payload.get("org_role") or "MEMBER"
    
    # Resolve Organization
    org = None
    if clerk_org_id:
        org = db.query(Organization).filter(Organization.clerk_org_id == clerk_org_id).first()
        if not org:
            # Create organization in local DB mapping to Clerk organization ID
            org = Organization(
                clerk_org_id=clerk_org_id,
                name=f"Org {clerk_org_id[:12]}"
            )
            db.add(org)
            db.commit()
            db.refresh(org)
    else:
        # Fallback personal workspace organization if user is not logged in under a Clerk org
        personal_org_id = f"personal_{clerk_user_id}"
        org = db.query(Organization).filter(Organization.clerk_org_id == personal_org_id).first()
        if not org:
            org = Organization(
                clerk_org_id=personal_org_id,
                name="Personal Workspace"
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            
    # Resolve User
    user = db.query(User).filter(User.clerk_user_id == clerk_user_id).first()
    if not user:
        # On first login, automatically create user record
        email = payload.get("email") or x_user_email or f"{clerk_user_id}@example.com"
        first_name = payload.get("first_name") or x_user_firstname or "First"
        last_name = payload.get("last_name") or x_user_lastname or "Last"
        
        user = User(
            clerk_user_id=clerk_user_id,
            organization_id=org.id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=org_role
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"[AUTH] Automatically created new User record for {email}.")
    else:
        # Keep organization and role synced in DB if user switches active org in Clerk
        if user.organization_id != org.id:
            user.organization_id = org.id
            user.role = org_role
            db.commit()
            db.refresh(user)
            print(f"[AUTH] Updated User workspace organization context to {org.name}.")
            
    return user
