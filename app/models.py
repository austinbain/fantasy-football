from sqlalchemy import (Column, Integer, String, Float, ForeignKey,
                         UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    ties = Column(Integer, default=0)
    points_for = Column(Float, default=0.0)
    points_against = Column(Float, default=0.0)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    pro_team = Column(String)
    injury_status = Column(String, default="ACTIVE")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    gsis_id = Column(String, nullable=True)
    espn_projected_points = Column(Float, nullable=True)

    team = relationship("Team", backref="roster")


class WeeklyStat(Base):
    __tablename__ = "weekly_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    fantasy_points = Column(Float, default=0.0)
    espn_projected_points = Column(Float, nullable=True)
    opponent_pro_team = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("player_id", "week", "season",
                          name="uq_player_week_season"),
    )


class DefenseVsPosition(Base):
    __tablename__ = "defense_vs_position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pro_team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    points_allowed = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("pro_team", "position", "week", "season",
                          name="uq_dvp"),
    )


class Matchup(Base):
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Float, default=0.0)
    away_score = Column(Float, default=0.0)
