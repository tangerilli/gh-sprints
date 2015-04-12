from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.dialects import postgresql
from database import Base
from datetime import datetime


class Sprint(Base):
    __tablename__ = 'sprints'
    id = Column(Integer, primary_key=True)
    name = Column(String(256))
    finished = Column(DateTime)
    data = Column(postgresql.JSON)
    snapshots = relationship('Snapshot', backref='sprint')
    locked = Column(Boolean)

    def __init__(self, name, finished=None, data=None):
        self.name = name
        self.finished = finished
        self.data = data


class Snapshot(Base):
    __tablename__ = 'snapshots'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'), nullable=True)
    issues = relationship('IssueSnapshot', backref='snapshot')
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, sprint):
        self.sprint = sprint

    @classmethod
    def get_most_recent_for_sprint(cls, sprint):
        return Snapshot.query.filter(Snapshot.sprint_id == sprint.id).order_by(
            Snapshot.timestamp.desc()).first()


class IssueSnapshot(Base):
    ISSUE_STATE_PICKUP = 0
    ISSUE_STATE_BUILDING = 1
    ISSUE_STATE_CR = 2
    ISSUE_STATE_DEPLOY = 3
    ISSUE_STATE_CLOSED = 4

    __tablename__ = 'issue_snapshots'
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer)
    points = Column(Integer)
    data = Column(postgresql.JSON)
    snapshot_id = Column(Integer, ForeignKey('snapshots.id'), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    state = Column(Integer)

    def __init__(self, issue_id, points, state, snapshot, data):
        self.issue_id = issue_id
        self.points = points
        self.snapshot = snapshot
        self.data = data
        self.state = state
