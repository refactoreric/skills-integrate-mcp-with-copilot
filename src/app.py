"""High School Management System API."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities",
)

current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

DATABASE_PATH = Path(os.getenv("ACTIVITIES_DB_PATH", current_dir / "activities.db"))

DEFAULT_ACTIVITIES = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}


class ActivityCreate(BaseModel):
    name: str
    description: str
    schedule: str
    max_participants: int = Field(gt=0)


class ActivityUpdate(BaseModel):
    description: str | None = None
    schedule: str | None = None
    max_participants: int | None = Field(default=None, gt=0)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,
                max_participants INTEGER NOT NULL CHECK (max_participants > 0)
            );
            CREATE TABLE IF NOT EXISTS participants (
                activity_name TEXT NOT NULL REFERENCES activities(name) ON DELETE CASCADE,
                email TEXT NOT NULL,
                PRIMARY KEY (activity_name, email)
            );
            """
        )
        for name, activity in DEFAULT_ACTIVITIES.items():
            connection.execute(
                """
                INSERT OR IGNORE INTO activities
                    (name, description, schedule, max_participants)
                VALUES (?, ?, ?, ?)
                """,
                (name, activity["description"], activity["schedule"], activity["max_participants"]),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO participants (activity_name, email) VALUES (?, ?)",
                [(name, email) for email in activity["participants"]],
            )


def activity_response(connection: sqlite3.Connection, name: str) -> dict:
    activity = connection.execute(
        "SELECT name, description, schedule, max_participants FROM activities WHERE name = ?",
        (name,),
    ).fetchone()
    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")
    participants = connection.execute(
        "SELECT email FROM participants WHERE activity_name = ? ORDER BY email",
        (name,),
    ).fetchall()
    return {
        "description": activity["description"],
        "schedule": activity["schedule"],
        "max_participants": activity["max_participants"],
        "participants": [participant["email"] for participant in participants],
    }


initialize_database()


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    with get_connection() as connection:
        names = connection.execute("SELECT name FROM activities ORDER BY name").fetchall()
        return {activity["name"]: activity_response(connection, activity["name"]) for activity in names}


@app.get("/activities/{activity_name}")
def get_activity(activity_name: str):
    with get_connection() as connection:
        return activity_response(connection, activity_name)


@app.post("/activities", status_code=201)
def create_activity(activity: ActivityCreate):
    with get_connection() as connection:
        try:
            connection.execute(
                "INSERT INTO activities (name, description, schedule, max_participants) VALUES (?, ?, ?, ?)",
                (activity.name, activity.description, activity.schedule, activity.max_participants),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Activity already exists")
        return activity_response(connection, activity.name)


@app.patch("/activities/{activity_name}")
def update_activity(activity_name: str, activity: ActivityUpdate):
    updates = activity.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one field is required")
    with get_connection() as connection:
        activity_response(connection, activity_name)
        if "max_participants" in updates:
            participant_count = connection.execute(
                "SELECT COUNT(*) AS count FROM participants WHERE activity_name = ?",
                (activity_name,),
            ).fetchone()["count"]
            if updates["max_participants"] < participant_count:
                raise HTTPException(status_code=400, detail="Capacity cannot be below participant count")
        assignments = ", ".join(f"{field} = ?" for field in updates)
        connection.execute(
            f"UPDATE activities SET {assignments} WHERE name = ?",
            [*updates.values(), activity_name],
        )
        return activity_response(connection, activity_name)


@app.delete("/activities/{activity_name}")
def delete_activity(activity_name: str):
    with get_connection() as connection:
        activity_response(connection, activity_name)
        connection.execute("DELETE FROM activities WHERE name = ?", (activity_name,))
        return {"message": f"Deleted {activity_name}"}


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity"""
    with get_connection() as connection:
        activity = connection.execute(
            "SELECT max_participants FROM activities WHERE name = ?", (activity_name,)
        ).fetchone()
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        participant_count = connection.execute(
            "SELECT COUNT(*) AS count FROM participants WHERE activity_name = ?", (activity_name,)
        ).fetchone()["count"]
        if participant_count >= activity["max_participants"]:
            raise HTTPException(status_code=400, detail="Activity is at capacity")
        try:
            connection.execute(
                "INSERT INTO participants (activity_name, email) VALUES (?, ?)",
                (activity_name, email),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="Student is already signed up")
        return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity"""
    with get_connection() as connection:
        if connection.execute(
            "SELECT 1 FROM activities WHERE name = ?", (activity_name,)
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        result = connection.execute(
            "DELETE FROM participants WHERE activity_name = ? AND email = ?",
            (activity_name, email),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=400, detail="Student is not signed up for this activity")
        return {"message": f"Unregistered {email} from {activity_name}"}
