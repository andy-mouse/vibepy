"""The Expense App: the role gate is the framework's, the self-approval rule is the App's."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import BaseModel

from vibepy_core import (
    AppDefinition,
    AppEntrypoint,
    ErrorCategory,
    ErrorInfo,
    NoConfig,
    Tool,
    ToolContext,
    ToolDefinition,
)


class Expense(BaseModel):
    id: int
    submitter: str
    amount: int
    status: str


class Submission(BaseModel):
    amount: int


class Approval(BaseModel):
    id: int


class Decision(BaseModel):
    expense: Expense | None = None
    failure: ErrorInfo | None = None


class Nothing(BaseModel):
    pass


class Expenses(BaseModel):
    expenses: list[Expense]


class Ledger:
    def __init__(self) -> None:
        self._rows: dict[int, Expense] = {}

    def submit(self, submitter: str, amount: int) -> Expense:
        row = Expense(
            id=len(self._rows) + 1, submitter=submitter, amount=amount, status="submitted"
        )
        self._rows[row.id] = row
        return row

    def approve(self, approver: str, expense_id: int) -> Decision:
        row = self._rows.get(expense_id)
        if row is None:
            return Decision(
                failure=ErrorInfo(
                    code="expense.not_found",
                    category=ErrorCategory.CALLER,
                    message=f"No expense {expense_id}",
                    details={"id": str(expense_id)},
                )
            )
        if row.submitter == approver:
            return Decision(
                failure=ErrorInfo(
                    code="expense.self_approval",
                    category=ErrorCategory.CALLER,
                    message="An expense is not approved by its submitter",
                    details={"id": str(expense_id), "submitter": approver},
                )
            )
        approved = row.model_copy(update={"status": "approved"})
        self._rows[expense_id] = approved
        return Decision(expense=approved)

    def all(self) -> list[Expense]:
        return list(self._rows.values())


@asynccontextmanager
async def expense_lifespan(_config: NoConfig) -> AsyncGenerator[Ledger]:
    yield Ledger()


async def submit_expense(ctx: ToolContext[Ledger], payload: Submission) -> Expense:
    return ctx.dependencies.submit(ctx.principal.id, payload.amount)


async def approve_expense(ctx: ToolContext[Ledger], payload: Approval) -> Decision:
    return ctx.dependencies.approve(ctx.principal.id, payload.id)


async def list_expenses(ctx: ToolContext[Ledger], _payload: Nothing) -> Expenses:
    return Expenses(expenses=ctx.dependencies.all())


EXPENSE_APP: AppDefinition[Ledger, NoConfig] = AppDefinition(
    app_id="expense-app",
    name="Expense",
    version="0.1.0",
    config=NoConfig,
    tools=[
        Tool(
            definition=ToolDefinition(
                name="submit_expense",
                description="Submit an expense",
                input_model=Submission,
                output_model=Expense,
                read_only=False,
            ),
            handler=submit_expense,
        ),
        Tool(
            definition=ToolDefinition(
                name="approve_expense",
                description="Approve another's expense",
                input_model=Approval,
                output_model=Decision,
                read_only=False,
                required_roles=frozenset({"manager"}),
            ),
            handler=approve_expense,
        ),
        Tool(
            definition=ToolDefinition(
                name="list_expenses",
                description="Every expense",
                input_model=Nothing,
                output_model=Expenses,
                read_only=True,
            ),
            handler=list_expenses,
        ),
    ],
    pages=[],
)

APP: AppEntrypoint[Ledger, NoConfig] = AppEntrypoint(
    definition=EXPENSE_APP, lifespan=expense_lifespan
)
