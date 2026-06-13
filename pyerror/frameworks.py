import json
from typing import Any

# Flask Integration Helper
def register_flask_error_handler(app: Any):
    """
    Registers a global error handler on a Flask application instance.
    Formats all uncaught exceptions into clean, human-readable JSON payloads.
    """
    try:
        from flask import jsonify
    except ImportError:
        raise ImportError("Flask is required to use register_flask_error_handler. Install it via 'pip install flask'.")

    import pyerror

    @app.errorhandler(Exception)
    def handle_exception(e):
        payload = json.loads(pyerror.to_json(e))
        status_code = 500
        if hasattr(e, "code"):  # Flask HTTPExceptions have code attribute
            status_code = e.code
        
        # Log to analytics automatically
        try:
            from pyerror.analytics import log_error
            log_error(e)
        except Exception:
            pass

        # Mirror diagnostics onto the active OpenTelemetry span, if any
        try:
            from pyerror import otel
            otel.record_exception(e)
        except Exception:
            pass

        # Send integration notifications
        try:
            from pyerror.integrations import notify_slack, notify_sentry, send_email
            notify_slack(e)
            notify_sentry(e)
            send_email(e)
        except Exception:
            pass
            
        return jsonify(payload), status_code

# FastAPI / Starlette Integration Middleware
try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse
    
    class FastAPIErrorMiddleware(BaseHTTPMiddleware):
        """
        FastAPI / Starlette middleware that catches all unhandled exceptions
        and returns a premium humanized JSON response.
        """
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            try:
                return await call_next(request)
            except Exception as exc:
                import pyerror
                payload = json.loads(pyerror.to_json(exc))
                
                # Log to analytics automatically
                try:
                    from pyerror.analytics import log_error
                    log_error(exc)
                except Exception:
                    pass

                # Mirror diagnostics onto the active OpenTelemetry span, if any
                try:
                    from pyerror import otel
                    otel.record_exception(exc)
                except Exception:
                    pass

                # Send integration notifications
                try:
                    from pyerror.integrations import notify_slack, notify_sentry, send_email
                    notify_slack(exc)
                    notify_sentry(exc)
                    send_email(exc)
                except Exception:
                    pass
                    
                return JSONResponse(
                    status_code=500,
                    content=payload
                )
except ImportError:
    # Graceful stub fallback if starlette/fastapi is not installed
    class FastAPIErrorMiddleware:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "FastAPI/Starlette is required to use FastAPIErrorMiddleware. "
                "Install them via 'pip install fastapi starlette'."
            )
