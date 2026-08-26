from app.domain import departments
from app.domain.departments import (
    DEPARTMENT_DESCRIPTIONS,
    Department,
    resolve_email,
)

FROM_TASK = {
    Department.HUMAN_RESOURCES: "human-resources@example.com",
    Department.HELP_DESK: "help-desk@example.com",
    Department.IT: "it@example.com",
    Department.KADRY: "kadry@example.com",
    Department.OTHER: "other@example.com",
}


def test_addresses_and_descriptions_match_the_task():
    for department, expected in FROM_TASK.items():
        assert resolve_email(department) == expected
        assert DEPARTMENT_DESCRIPTIONS[department].strip()


def test_missing_entry_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.delitem(departments.DEPARTMENT_EMAILS, Department.IT)
    assert resolve_email(Department.IT) == FROM_TASK[Department.OTHER]
