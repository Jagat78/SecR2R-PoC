from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    robot_id: str
    attributes: dict[str, str]


class RegisterResponse(BaseModel):
    robot_id: str
    status: str


class M1A(BaseModel):
    session_id: str
    from_robot: str
    to_robot: str
    c1: str
    c3: str
    c4: str
    c5: str
    t_a: int


class M1S(BaseModel):
    session_id: str
    y1: str
    y2: str
    y3: str
    t1_s: int
    from_robot: str
    to_robot: str


class MB(BaseModel):
    session_id: str
    from_robot: str
    to_robot: str
    w1: str
    w3: str
    w4: str
    t_b: int


class M2S(BaseModel):
    session_id: str
    y4: str
    y5: str
    y6: str
    t2_s: int


class SessionRunRequest(BaseModel):
    target_robot: str = Field(default="R_B")
    attributes: dict[str, str]


class SessionRunResponse(BaseModel):
    session_id: str
    accepted: bool
    reason: str
    session_key: str | None = None
