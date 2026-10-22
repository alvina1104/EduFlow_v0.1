from sqladmin import ModelView
from myproject.database.models import User, Student, Group, Contract, Payment


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.username, User.role, User.is_active]
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"


class StudentAdmin(ModelView, model=Student):
    column_list = [Student.id, Student.student_number, Student.group_id]
    name = "Студент"
    name_plural = "Студенты"
    icon = "fa-solid fa-graduation-cap"


class GroupAdmin(ModelView, model=Group):
    column_list = [Group.id, Group.name, Group.course_name, Group.start_date, Group.end_date]
    name = "Группа"
    name_plural = "Группы"
    icon = "fa-solid fa-users"


class ContractAdmin(ModelView, model=Contract):
    column_list = [Contract.id, Contract.student_id, Contract.total_amount, Contract.monthly_payment, Contract.status]
    name = "Контракт"
    name_plural = "Контракты"
    icon = "fa-solid fa-file-contract"


class PaymentAdmin(ModelView, model=Payment):
    column_list = [Payment.id, Payment.contract_id, Payment.amount, Payment.status, Payment.created_at]
    name = "Платёж"
    name_plural = "Платежи"
    icon = "fa-solid fa-money-bill"