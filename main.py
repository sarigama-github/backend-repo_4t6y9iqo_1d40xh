import os
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, Employee, Department, LeaveRequest, Attendance, Payroll, PayrollItem, Session, SalaryStructure, BankDetails, StatutoryAccounts

app = FastAPI(title="HRMS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility functions

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def now_utc() -> datetime:
    return datetime.utcnow()


# Simple auth (demo only): token in memory stored in DB collection `session`
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: str
    role: str
    name: str
    user_id: str


def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    session = db["session"].find_one({"token": token})
    if not session:
        return None
    user = db["user"].find_one({"_id": session.get("user_id")})
    return user


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # For demo: compare password hash field directly (in real apps use bcrypt)
    if user.get("password_hash") != payload.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = os.urandom(24).hex()
    expires = now_utc() + timedelta(days=7)
    db["session"].insert_one({"user_id": user["_id"], "token": token, "expires_at": expires})
    return LoginResponse(token=token, role=user.get("role", "employee"), name=user.get("name", ""), user_id=str(user["_id"]))


@app.post("/auth/logout")
def logout(token: str):
    db["session"].delete_one({"token": token})
    return {"success": True}


# Superadmin: create users and employee profiles
class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str
    password: str


@app.post("/admin/users")
def create_user(req: CreateUserRequest):
    if db["user"].find_one({"email": req.email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    user_doc = User(name=req.name, email=req.email, role=req.role, password_hash=req.password, is_active=True)
    user_id = create_document("user", user_doc)
    # create empty employee profile if role is employee
    if req.role == "employee":
        emp = Employee(user_id=user_id)
        create_document("employee", emp)
    return {"_id": user_id}


@app.get("/admin/users")
def list_users():
    users = get_documents("user")
    for u in users:
        u["_id"] = str(u["_id"]) if "_id" in u else None
    return users


# Departments
class DepartmentRequest(BaseModel):
    name: str
    code: str
    description: Optional[str] = None


@app.post("/admin/departments")
def create_department(req: DepartmentRequest):
    dep = Department(**req.model_dump())
    dep_id = create_document("department", dep)
    return {"_id": dep_id}


@app.get("/admin/departments")
def get_departments():
    deps = get_documents("department")
    for d in deps:
        d["_id"] = str(d["_id"]) if "_id" in d else None
    return deps


# Employee profile update
class EmployeeUpdateRequest(BaseModel):
    designation: Optional[str] = None
    department_id: Optional[str] = None
    work_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    bank: Optional[BankDetails] = None
    statutory: Optional[StatutoryAccounts] = None
    salary: Optional[SalaryStructure] = None


@app.put("/employee/{user_id}")
def update_employee(user_id: str, req: EmployeeUpdateRequest):
    emp = db["employee"].find_one({"user_id": user_id})
    if not emp:
        # create profile if not exists
        create_document("employee", Employee(user_id=user_id))
    update_data = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    db["employee"].update_one({"user_id": user_id}, {"$set": update_data}, upsert=True)
    return {"success": True}


@app.get("/employee/{user_id}")
def get_employee(user_id: str):
    emp = db["employee"].find_one({"user_id": user_id})
    if not emp:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    emp["_id"] = str(emp.get("_id"))
    return emp


# Attendance
class AttendanceRequest(BaseModel):
    date: date
    status: str = "present"
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None


@app.post("/attendance/{user_id}")
def mark_attendance(user_id: str, req: AttendanceRequest):
    data = {**req.model_dump(), "user_id": user_id}
    create_document("attendance", data)
    return {"success": True}


@app.get("/attendance/{user_id}")
def get_attendance(user_id: str, month: Optional[int] = None, year: Optional[int] = None):
    query = {"user_id": user_id}
    if month and year:
        # naive range filter by month
        start = datetime(year, month, 1)
        end = datetime(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        query["date"] = {"$gte": start.date(), "$lt": end.date()}
    items = get_documents("attendance", query)
    for i in items:
        i["_id"] = str(i["_id"]) if "_id" in i else None
    return items


# Leaves
class LeaveCreateRequest(BaseModel):
    start_date: date
    end_date: date
    leave_type: str
    reason: Optional[str] = None


@app.post("/leaves/{user_id}")
def apply_leave(user_id: str, req: LeaveCreateRequest):
    leave = LeaveRequest(user_id=user_id, start_date=req.start_date, end_date=req.end_date, leave_type=req.leave_type, reason=req.reason)
    leave_id = create_document("leaverequest", leave)
    return {"_id": leave_id}


@app.get("/leaves/{user_id}")
def list_leaves(user_id: str):
    items = get_documents("leaverequest", {"user_id": user_id})
    for i in items:
        i["_id"] = str(i["_id"]) if "_id" in i else None
    return items


@app.post("/leaves/approve/{leave_id}")
def approve_leave(leave_id: str, approver_id: str, status: str = "approved"):
    db["leaverequest"].update_one({"_id": to_object_id(leave_id)}, {"$set": {"status": status, "approver_id": approver_id}})
    return {"success": True}


# Payroll
class PayrollGenerateRequest(BaseModel):
    month: int
    year: int


@app.post("/payroll/generate/{user_id}")
def generate_payslip(user_id: str, req: PayrollGenerateRequest):
    emp = db["employee"].find_one({"user_id": user_id})
    if not emp or not emp.get("salary"):
        raise HTTPException(status_code=400, detail="Salary structure not defined")
    salary = emp["salary"]
    basic = float(salary.get("basic", 0))
    hra = float(salary.get("hra", 0))
    special = float(salary.get("special_allowance", 0))
    other = float(salary.get("other_earnings", 0))
    gross = basic + hra + special + other
    deductions = float(salary.get("deductions", 0))
    net = gross - deductions

    payroll = Payroll(
        user_id=user_id,
        month=req.month,
        year=req.year,
        earnings=[
            PayrollItem(label="Basic", amount=basic),
            PayrollItem(label="HRA", amount=hra),
            PayrollItem(label="Special Allowance", amount=special),
            PayrollItem(label="Other Earnings", amount=other),
        ],
        deductions=[PayrollItem(label="Deductions", amount=deductions)],
        gross=gross,
        net=net,
        status="generated",
    )
    slip_id = create_document("payroll", payroll)
    return {"_id": slip_id, "gross": gross, "net": net}


@app.get("/payroll/{user_id}")
def list_payslips(user_id: str):
    slips = get_documents("payroll", {"user_id": user_id})
    for s in slips:
        s["_id"] = str(s["_id"]) if "_id" in s else None
    return slips


@app.get("/")
def root():
    return {"message": "HRMS API running"}


@app.get("/schema")
def schema_summary():
    # return simple names for viewer
    return {
        "collections": [
            "user", "employee", "department", "attendance", "leaverequest", "payroll", "session"
        ]
    }


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            collections = db.list_collection_names()
            response["collections"] = collections[:10]
            response["database"] = "✅ Connected & Working"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
