"""Prior synthetic tests opt in to demo access; production defaults stay protected."""

from app.main import create_app


def demo_app(*args, **kwargs):
    return create_app(*args, auth_mode='demo', **kwargs)
