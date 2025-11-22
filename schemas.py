"""
Database Schemas for HRMS

Each Pydantic model maps to a MongoDB collection (lowercased class name).
Use these models for validation when creating or updating documents.
"""

from typing import Optional, List, Dict
from pydantic import BaseModel, Field, EmailStr
from datetime import date, datetime

# --- Auth / Users ---
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    role: str = Field(..., description="User role: superadmin | employee")
    password_hash: str = Field(..., description="Password hash (server-side only)")
    is_active: bool = Field(True, description="Whether user is active")

# --- Departments ---
class Department(BaseModel):
    name: str = Field(...)
    code: str = Field(...)
    description: Optional[str] = None

# --- Employee profile & accounts ---
class BankDetails(BaseModel):
    account_holder: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    bank_name: Optional[str] = None
    branch: Optional[str] = None

class StatutoryAccounts(BaseModel):
    pf_number: Optional[str] = Field(None, description="Provident Fund number (PF)")
    uan: Optional[str] = Field(None, description="Universal Account Number")
    esi_number: Optional[str] = Field(None, description="ESI number")
    pan: Optional[str] = None

class SalaryStructure(BaseModel):
    basic: float = 0
    hra: float = 0
    special_allowance: float = 0
    other_earnings: float = 0
    deductions: float = 0

class Employee(BaseModel):
    user_id: str = Field(..., description="Reference to user _id")
    department_id: Optional[str] = None
    designation: Optional[str] = None
    join_date: Optional[date] = None
    work_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    bank: Optional[BankDetails] = None
    statutory: Optional[StatutoryAccounts] = None
    salary: Optional[SalaryStructure] = None

# --- Attendance ---
class Attendance(BaseModel):
    user_id: str
    date: date
    status: str = Field("present", description="present | absent | leave")
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None

# --- Leave ---
class LeaveRequest(BaseModel):
    user_id: str
    start_date: date
    end_date: date
    leave_type: str = Field(..., description="sick | casual | earned | unpaid")
    reason: Optional[str] = None
    status: str = Field("pending", description="pending | approved | rejected")
    approver_id: Optional[str] = None

# --- Payroll & Payslips ---
class PayrollItem(BaseModel):
    label: str
    amount: float

class Payroll(BaseModel):
    user_id: str
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2200)
    earnings: List[PayrollItem] = []
    deductions: List[PayrollItem] = []
    gross: float = 0
    net: float = 0
    generated_by: Optional[str] = None
    status: str = Field("generated", description="generated | processed | paid")

# --- Sessions (token storage) ---
class Session(BaseModel):
    user_id: str
    token: str
    expires_at: datetime
