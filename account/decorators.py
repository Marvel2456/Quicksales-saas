from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from .models import Branch, CustomUser
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from functools import wraps
from django.contrib.auth.views import redirect_to_login


def role_required(roles, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
    def decorator(function):
        actual_decorator = user_passes_test(
            lambda u: u.is_authenticated and u.is_active and u.role in roles,
            login_url=login_url,
            redirect_field_name=redirect_field_name
        )
        return actual_decorator(function)
    return decorator


# def role_required(roles, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     def decorator(view_func):
#         @wraps(view_func)
#         def _wrapped_view(request, *args, **kwargs):
#             user = request.user
#             if user.is_authenticated and user.is_active and user.role in roles:
#                 return view_func(request, *args, **kwargs)
#             return redirect_to_login(request.get_full_path(), login_url, redirect_field_name)
#         return _wrapped_view
#     return decorator



# def for_admin(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'owner',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator

# def for_sub_admin(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'manager',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator

# def for_staff(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.role == 'sales',
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator

# def is_unsubscribed(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url='login'):
#     actual_decorator = user_passes_test(
#         lambda u: u.is_active and u.is_subscribed==True,
#         login_url=login_url,
#         redirect_field_name=redirect_field_name
#     )
#     if function:
#         return actual_decorator(function)
#     return actual_decorator


# def branch_required(branch):
#     def decorator(view_func):
#         def wrapped_view(request, pk, *args, **kwargs):
#             if request.user.is_authenticated and request.user.is_admin==False:
#                 branch = Branch.objects.get(id=pk)
#                 user_branch = CustomUser.objects.filter(branch_id = pk)
#                 if user_branch.id == branch.id:
#                     return view_func(request, pk, *args, **kwargs)
#                 else:
#                     return redirect('/index/'+str(branch.id)) 
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator



        

# from django.shortcuts import redirect
# from django.contrib.auth.decorators import login_required

# def branch_required(desired_branch):
#     def decorator(view_func):
#         def wrapped_view(request, *args, **kwargs):
#             if request.user.is_authenticated:
#                 if request.user.branch == desired_branch:
#                     return view_func(request, *args, **kwargs)
#                 else:
#                     return redirect('unauthorized')
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator

# @branch_required('sales')
# @login_required
# def my_view(request):
#     # Code for the view goes here
#     pass


# from django.shortcuts import redirect
# from django.contrib.auth.decorators import login_required
# from your_app.models import Branch, CustomUser

# def branch_required(desired_branch_id):
#     def decorator(view_func):
#         def wrapped_view(request, *args, **kwargs):
#             if request.user.is_authenticated:
#                 user_branch = CustomUser.objects.get(id=request.user.id).branch
#                 if user_branch.id == desired_branch_id:
#                     return view_func(request, *args, **kwargs)
#                 else:
#                     return redirect('unauthorized')
#             else:
#                 return redirect('login')
#         return wrapped_view
#     return decorator

# @branch_required(1)
# @login_required
# def my_view(request):
#     # Code for the view goes here
#     pass
