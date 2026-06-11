from typing import List, Optional, Type, Dict, Any

def create(
    name: str, 
    message: str = "", 
    suggestions: Optional[List[str]] = None, 
    base: Type[Exception] = Exception
) -> Type[Exception]:
    """
    Dynamically creates a custom Exception class.
    
    The resulting class will support keyword-argument formatting for its message
    and carry custom suggestions that the formatter will automatically pick up.
    
    Example:
        UserNotFound = error.create(
            "UserNotFound", 
            message="User {user_id} was not found", 
            suggestions=["Check the ID", "Confirm user exists before lookup"]
        )
        
        raise UserNotFound(user_id=143)
    """
    custom_suggestions = suggestions.copy() if suggestions is not None else []

    def __init__(self, *args, **kwargs):
        # Store suggestions on instance
        self.__suggestions__ = custom_suggestions.copy()
        self.__arguments__ = kwargs.copy()
        
        # Determine the formatted message
        if kwargs and message:
            try:
                # Save kwargs directly on the exception instance for easy access
                for k, v in kwargs.items():
                    setattr(self, k, v)
                formatted_msg = message.format(**kwargs)
            except Exception:
                formatted_msg = message
        elif args:
            if len(args) == 1 and isinstance(args[0], dict) and message:
                try:
                    formatted_msg = message.format(**args[0])
                except Exception:
                    formatted_msg = message
            else:
                try:
                    formatted_msg = message.format(*args) if message else str(args[0])
                except Exception:
                    formatted_msg = message or str(args)
        else:
            formatted_msg = message

        # Initialize base exception class
        super(base, self).__init__(formatted_msg)

    # Construct the custom exception class
    custom_class = type(name, (base,), {
        "__init__": __init__,
        "__suggestions__": custom_suggestions,
        "__translation__": f"A custom exception '{name}' was raised.",
        "__why__": f"The application raised a custom error '{name}' indicating a specific business or application rule violation."
    })
    
    return custom_class
