from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


def mobile_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException):
        if isinstance(response.data, dict) and "code" not in response.data:
            code = exc.get_codes()
            if isinstance(code, str):
                response.data["code"] = code
    return response

