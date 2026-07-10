import os
import jwt
import requests
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Depends, status
from sqlalchemy.orm import Session
from database import get_db, User, Organization, Vendor

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
    
    # Resolve Organization: always map to the primary seeded organization for single-tenant demo context
    org = db.query(Organization).first()
    if not org:
        org = Organization(
            clerk_org_id=clerk_org_id or "org_2tJ8XWn6qE",
            name="Acme Corporation"
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
        
        # Check if this is the default Administrator
        if email == "joshiamogh1234@gmail.com":
            role = "ADMINISTRATOR"
            status = "APPROVED"
            vendor_id = None
        else:
            # Check if the email matches a known vendor in the DB
            vendor = db.query(Vendor).filter(Vendor.email == email, Vendor.organization_id == org.id).first()
            if vendor:
                role = "SUPPLIER_USER"
                status = "APPROVED"
                vendor_id = vendor.id
            else:
                # Check if this email was pre-approved / pre-seeded as a manager
                pre_seeded_user = db.query(User).filter(User.email == email, User.clerk_user_id == "pending").first()
                if pre_seeded_user:
                    pre_seeded_user.clerk_user_id = clerk_user_id
                    pre_seeded_user.first_name = first_name
                    pre_seeded_user.last_name = last_name
                    pre_seeded_user.status = "APPROVED"
                    db.commit()
                    return pre_seeded_user
                
                # Otherwise, new signup starts as PENDING_APPROVAL
                role = "PENDING_APPROVAL"
                status = "PENDING"
                vendor_id = None
            
        user = User(
            clerk_user_id=clerk_user_id,
            organization_id=org.id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            vendor_id=vendor_id,
            status=status
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"[AUTH] Automatically created new User record for {email} with role {role} and status {status}.")
    else:
        # If this is the default Administrator, ensure correct role and status
        if user.email == "joshiamogh1234@gmail.com" and user.role != "ADMINISTRATOR":
            user.role = "ADMINISTRATOR"
            user.status = "APPROVED"
            db.commit()
            db.refresh(user)
        # Keep organization and role synced in DB if user switches active org in Clerk
        elif user.organization_id != org.id:
            user.organization_id = org.id
            user.role = org_role
            db.commit()
            db.refresh(user)
            print(f"[AUTH] Updated User workspace organization context to {org.name}.")
            
    return user
