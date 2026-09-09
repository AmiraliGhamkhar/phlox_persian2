from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from server.database.config.manager import config_manager

router = APIRouter()


@router.get("/user")
def get_user_settings():
    """Retrieve the current user settings."""
    return JSONResponse(content=config_manager.get_user_settings())


@router.post("/user")
def update_user_settings(data: dict = Body(...)):
    """Update user settings with provided data."""
    config_manager.update_user_settings(data)
    return {"message": "User settings updated successfully"}


@router.post("/user/mark_splash_complete")
def mark_splash_complete():
    """Mark the splash screen as completed for the current user."""
    current_settings = config_manager.get_user_settings()
    current_settings["has_completed_splash_screen"] = True
    config_manager.update_user_settings(current_settings)
    return {"message": "Splash screen marked as completed."}
