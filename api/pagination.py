from rest_framework.pagination import PageNumberPagination


class MobilePageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def paginate_queryset(request, queryset, serializer_class, extra_data=None):
    """Paginate a queryset with MobilePageNumberPagination and return a standard DRF Response."""
    paginator = MobilePageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(page, many=True)
    response = paginator.get_paginated_response(serializer.data)
    if extra_data and isinstance(response.data, dict):
        response.data.update(extra_data)
    return response


def paginate_list(request, items, extra_data=None):
    """Paginate an already-evaluated list (e.g. audit dicts) with MobilePageNumberPagination."""
    paginator = MobilePageNumberPagination()
    page = paginator.paginate_queryset(items, request)
    response = paginator.get_paginated_response(page)
    if extra_data and isinstance(response.data, dict):
        response.data.update(extra_data)
    return response

