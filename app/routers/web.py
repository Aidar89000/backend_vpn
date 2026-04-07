from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(tags=['web'])


@router.get('/')
async def index():
    return RedirectResponse(url='/', status_code=307)


@router.get('/login')
async def login_page():
    return RedirectResponse(url='/', status_code=307)


@router.get('/register')
async def register_page():
    return RedirectResponse(url='/', status_code=307)


@router.get('/profile')
async def profile_page():
    return RedirectResponse(url='/', status_code=307)


@router.get('/logout')
async def logout_page():
    return RedirectResponse(url='/', status_code=307)
