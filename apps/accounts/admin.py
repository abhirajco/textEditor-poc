from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, RBAC


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display   = ('email', 'full_name', 'group', 'role', 'is_active', 'is_staff')
    list_filter    = ('group', 'role', 'is_active')
    search_fields  = ('email', 'full_name')
    ordering       = ('-date_joined',)
    fieldsets      = (
        (None,          {'fields': ('email', 'password')}),
        ('Personal',    {'fields': ('full_name',)}),
        ('Role & Group',{'fields': ('group', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets  = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'full_name', 'group', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(RBAC)
class RBACAdmin(admin.ModelAdmin):
    list_display  = ('application_group', 'application_area', 'application_action')
    list_filter   = ('application_area', 'application_action')
    search_fields = ('application_group__name',)
