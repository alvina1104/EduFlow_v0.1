from sqladmin import Admin
from myproject.database.db import engine
from myproject.admin.view import UserAdmin, StudentAdmin, GroupAdmin, ContractAdmin, PaymentAdmin


def setup_admin(app):
    admin = Admin(app, engine)
    admin.add_view(UserAdmin)
    admin.add_view(StudentAdmin)
    admin.add_view(GroupAdmin)
    admin.add_view(ContractAdmin)
    admin.add_view(PaymentAdmin)
    return admin