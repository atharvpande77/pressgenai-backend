import openai
from decimal import Decimal, ROUND_HALF_UP

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.models import ChatSessions

client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

POLICE_HELPDESK_SYSTEM_PROMPT = """You are an official Nagpur City Police helpdesk assistant.

Answer only general informational queries asked under "Other Enquiry".
Do NOT handle emergencies, complaints, FIRs, legal accusations, or urgent situations.
If the message is urgent or a complaint, instruct the user to contact the nearest police station or dial 112.

Respond in the same language as the user (English or Marathi).
Keep replies clear, polite, and concise.
Do not speculate or give legal advice.
If information is unavailable, say so clearly."""


RETIREMENT_DEFAULT_INFLATION_RATE = Decimal("6")
RETIREMENT_DEFAULT_RETURN_RATE = Decimal("11")
RETIREMENT_DEFAULT_CORPUS_MULTIPLIER_YEARS = 20
RETIREMENT_INPUT_KEYS = {
    "age",
    "expected_age_to_retire",
    "current_monthly_expenses",
    "retirement_goal_type",
    "monthly_goal_amount",
    "has_loans",
    "loan_amount",
    "has_existing_retirement_savings",
    "existing_savings_description",
    "existing_savings_amount",
    "first_name",
    "phone_number",
}


async def get_police_helpdesk_response(query: str, language: str = "English") -> str:
    """
    Calls OpenAI chat completions API to get a response for police helpdesk queries.
    """
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"{POLICE_HELPDESK_SYSTEM_PROMPT}",
            },
            {
                "role": "user",
                "content": query,
            },
        ],
        temperature=0.3,
        max_tokens=500,
    )

    return response.choices[0].message.content


def inject_initial_context(thread_id: str, goal: str, client):
    goal_map = {
        "retirement": "Retirement planning",
        "child_education": "Child education planning",
        "savings": "Savings with protection",
        "human_life_value": "Human Life Value assessment",
    }

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=f"""
            The user has already selected the primary planning objective as:
            {goal_map.get(goal, goal)}.

            Do NOT ask the user to choose a planning goal again.
            Proceed with questions relevant to this objective only.
            """,
    )


TABLE_NAME = "police_whatapp_bot_session_store"


async def check_if_message_after_ama(ddb, conversation_id: str, message: str) -> bool:
    """
    Tracks if "Ask me anything!" has been reached in a conversation.
    Returns True if conversation is past AMA state and should call GPT.
    """
    table = await ddb.Table(TABLE_NAME)

    if message.lower() == "ask me anything!":
        await table.put_item(
            Item={
                "conversation_id": conversation_id,
                "ama_reached": True,
                "language": "English",
            }
        )
        return False

    if message == "à¤•à¥‹à¤£à¤¤à¥‡à¤¹à¥€ à¤ªà¥à¤°à¤¶à¥à¤¨ à¤µà¤¿à¤šà¤¾à¤°à¤¾":
        await table.put_item(
            Item={
                "conversation_id": conversation_id,
                "ama_reached": True,
                "language": "Marathi",
            }
        )
        return False

    response = await table.get_item(Key={"conversation_id": conversation_id})
    item = response.get("Item", {})
    return item.get("ama_reached", False)


async def get_conversation_by_id(ddb, conversation_id: str) -> dict:
    """Returns the conversation data from DynamoDB, defaults to empty dict."""
    table = await ddb.Table(TABLE_NAME)
    response = await table.get_item(Key={"conversation_id": conversation_id})
    return response.get("Item", {"language": "English"})


async def get_curr_location_jurisdiction_and_nearest_station(
    session: AsyncSession, lat: float, lon: float
):
    """
    Get containing police station based on current location.
    """
    containing_result = await session.execute(
        text(
            """
            SELECT
                id,
                name,
                address,
                lat,
                lon,
                pi_name,
                pi_phone,
                zone,
                ST_Distance(
                    ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                ) as distance_meters
            FROM police_stations
            WHERE ST_Contains(
                boundary,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            )
            LIMIT 1
            """
        ),
        {"lat": lat, "lon": lon},
    )
    containing_station = containing_result.fetchone()

    return {
        "containing_station": {
            "id": str(containing_station.id),
            "name": containing_station.name,
            "address": containing_station.address,
            "lat": containing_station.lat,
            "lon": containing_station.lon,
            "pi_name": containing_station.pi_name,
            "pi_phone": containing_station.pi_phone,
            "zone": containing_station.zone,
            "distance_meters": float(containing_station.distance_meters),
        }
        if containing_station
        else {},
    }


async def send_message_to_user(message: str, phone: str):
    wati_api_base_url = "https://live-mt-server.wati.io"
    wati_url = f"{wati_api_base_url}/{settings.WATI_TENANT_ID}/api/v1/sendSessionMessage/{phone}"

    async with httpx.AsyncClient() as http_client:
        try:
            await http_client.post(
                wati_url,
                params={"messageText": message},
                headers={"Authorization": settings.WATI_API_ACCESS_TOKEN},
            )

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to send message via WATI: {e.response.text}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Error connecting to WATI API: {str(e)}",
            )


async def extract_fields(
    user_message: str,
    assistant_message: str,
    session: dict,
):
    ...


def _to_decimal(value, default: Decimal | None = Decimal("0")) -> Decimal | None:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _round_to_nearest_500(amount: Decimal) -> int:
    if amount <= 0:
        return 0
    rounded = (amount / Decimal("500")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("500")
    return int(rounded)


def _normalize_inputs(function_args: dict) -> dict:
    normalized = dict(function_args or {})
    if "retirement_age" in normalized and "expected_age_to_retire" not in normalized:
        normalized["expected_age_to_retire"] = normalized["retirement_age"]
    if "existing_retirement_savings" in normalized and "has_existing_retirement_savings" not in normalized:
        normalized["has_existing_retirement_savings"] = normalized["existing_retirement_savings"]
    if "existing_savings" in normalized and "existing_savings_amount" not in normalized:
        normalized["existing_savings_amount"] = normalized["existing_savings"]
    return normalized


def _extract_existing_inputs(collected_data: dict | None) -> dict:
    collected_data = collected_data if isinstance(collected_data, dict) else {}
    inputs = collected_data.get("inputs", {})
    if isinstance(inputs, dict):
        return dict(inputs)
    return {k: v for k, v in collected_data.items() if k != "calculation"}


def _merge_non_null(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    for key, value in incoming.items():
        if value is not None:
            merged[key] = value
    return merged


def calculate_retirement_plan_payload(raw_inputs: dict) -> dict:
    inputs = _normalize_inputs(raw_inputs or {})
    missing_fields: list[str] = []
    validation_errors: list[str] = []

    age = inputs.get("age")
    expected_age_to_retire = inputs.get("expected_age_to_retire")
    if age is None:
        missing_fields.append("age")
    if expected_age_to_retire is None:
        missing_fields.append("expected_age_to_retire")

    retirement_goal_type = inputs.get("retirement_goal_type", "lifestyle")
    monthly_goal_amount = inputs.get("monthly_goal_amount")
    monthly_expenses = inputs.get("current_monthly_expenses")
    if retirement_goal_type == "goal":
        if monthly_goal_amount is None:
            missing_fields.append("monthly_goal_amount")
    elif monthly_expenses is None:
        missing_fields.append("current_monthly_expenses")

    if missing_fields:
        return {
            "status": "missing_inputs",
            "missing_fields": sorted(set(missing_fields)),
            "inputs_used": inputs,
        }

    age = int(age)
    expected_age_to_retire = int(expected_age_to_retire)
    years_to_retirement = expected_age_to_retire - age
    if years_to_retirement <= 0:
        validation_errors.append("expected_age_to_retire must be greater than age")

    annual_inflation_rate = _to_decimal(inputs.get("annual_inflation_rate"), RETIREMENT_DEFAULT_INFLATION_RATE)
    annual_return_rate = _to_decimal(inputs.get("annual_return_rate"), RETIREMENT_DEFAULT_RETURN_RATE)
    corpus_multiplier_years = int(
        inputs.get("corpus_multiplier_years", RETIREMENT_DEFAULT_CORPUS_MULTIPLIER_YEARS)
    )
    if annual_inflation_rate is None or annual_inflation_rate < 0:
        validation_errors.append("annual_inflation_rate must be non-negative")
    if annual_return_rate is None or annual_return_rate < 0:
        validation_errors.append("annual_return_rate must be non-negative")
    if corpus_multiplier_years <= 0:
        validation_errors.append("corpus_multiplier_years must be greater than 0")

    if validation_errors:
        return {
            "status": "invalid_inputs",
            "errors": validation_errors,
            "inputs_used": inputs,
        }

    monthly_expenses_dec = _to_decimal(monthly_expenses) or Decimal("0")
    monthly_goal_amount_dec = _to_decimal(monthly_goal_amount) or Decimal("0")
    existing_savings_amount = _to_decimal(inputs.get("existing_savings_amount")) or Decimal("0")
    inflation_factor = Decimal("1") + (annual_inflation_rate / Decimal("100"))
    growth_factor = Decimal("1") + (annual_return_rate / Decimal("100"))
    inflated_expenses = monthly_expenses_dec * (inflation_factor ** years_to_retirement)

    lifestyle_corpus = inflated_expenses * Decimal("12") * Decimal(corpus_multiplier_years)
    corpus_needed = (
        monthly_goal_amount_dec * Decimal("12") * Decimal(corpus_multiplier_years)
        if retirement_goal_type == "goal"
        else lifestyle_corpus
    )

    fv_existing_savings = existing_savings_amount * (growth_factor ** years_to_retirement)
    gap = max(Decimal("0"), corpus_needed - fv_existing_savings)

    monthly_return = (annual_return_rate / Decimal("100")) / Decimal("12")
    months = years_to_retirement * 12
    if gap == 0:
        monthly_sip = Decimal("0")
    elif months <= 0:
        monthly_sip = Decimal("0")
    elif monthly_return == 0:
        monthly_sip = gap / Decimal(months)
    else:
        annuity_factor = ((Decimal("1") + monthly_return) ** months - Decimal("1")) / monthly_return
        monthly_sip = gap / annuity_factor if annuity_factor > 0 else Decimal("0")

    sip_low = _round_to_nearest_500(monthly_sip * Decimal("0.9"))
    sip_high = _round_to_nearest_500(monthly_sip * Decimal("1.1"))

    warnings = []
    if years_to_retirement < 5:
        warnings.append("FEWER_THAN_5_YEARS")
    if corpus_needed > 0 and gap >= (corpus_needed * Decimal("0.60")):
        warnings.append("LARGE_GAP")
    if fv_existing_savings >= corpus_needed:
        warnings.append("CORPUS_ALREADY_COVERED")

    has_loans = inputs.get("has_loans")
    loan_amount = _to_decimal(inputs.get("loan_amount")) or Decimal("0")
    if has_loans and monthly_expenses_dec > 0 and loan_amount >= (monthly_expenses_dec * Decimal("24")):
        warnings.append("LARGE_LOAN_BURDEN")

    scenario = inputs.get("scenario", "base")
    monthly_sip_override = _to_decimal(inputs.get("monthly_sip_override"), None)
    reality_check = None
    if scenario == "reality_check" and monthly_sip_override is not None:
        if monthly_return == 0:
            fv_from_override = monthly_sip_override * Decimal(months)
        else:
            annuity_factor = ((Decimal("1") + monthly_return) ** months - Decimal("1")) / monthly_return
            fv_from_override = monthly_sip_override * annuity_factor
        projected_total = fv_existing_savings + fv_from_override
        projected_shortfall = max(Decimal("0"), corpus_needed - projected_total)
        reality_check = {
            "monthly_sip_override": int(monthly_sip_override.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "projected_corpus_with_override": int(projected_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
            "projected_shortfall": int(projected_shortfall.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        }

    return {
        "status": "success",
        "inputs_used": {
            "age": age,
            "expected_age_to_retire": expected_age_to_retire,
            "retirement_goal_type": retirement_goal_type,
            "current_monthly_expenses": float(monthly_expenses_dec),
            "monthly_goal_amount": float(monthly_goal_amount_dec),
            "existing_savings_amount": float(existing_savings_amount),
            "annual_inflation_rate": float(annual_inflation_rate),
            "annual_return_rate": float(annual_return_rate),
            "corpus_multiplier_years": corpus_multiplier_years,
            "has_loans": has_loans,
            "loan_amount": float(loan_amount),
        },
        "years_to_retirement": years_to_retirement,
        "expenses_at_retirement_monthly": int(inflated_expenses.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "lifestyle_based_corpus": int(lifestyle_corpus.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "corpus_needed": int(corpus_needed.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "future_value_existing_savings": int(fv_existing_savings.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "gap": int(gap.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "monthly_sip": int(monthly_sip.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        "sip_low": sip_low,
        "sip_high": sip_high,
        "warnings": warnings,
        "reality_check": reality_check,
    }


async def update_chat_session_with_extracted_data(
    db: AsyncSession,
    session_id: str,
    thread_id: str,
    function_args: dict,
):
    result = await db.execute(
        select(ChatSessions).where(
            and_(ChatSessions.session_id == session_id, ChatSessions.thread_id == thread_id)
        )
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        return {"status": "error", "message": "session_not_found"}

    normalized_args = _normalize_inputs(function_args)
    current_collected_data = chat_session.collected_data if isinstance(chat_session.collected_data, dict) else {}
    current_inputs = _extract_existing_inputs(current_collected_data)
    incoming_inputs = {k: normalized_args.get(k) for k in RETIREMENT_INPUT_KEYS if k in normalized_args}
    merged_inputs = _merge_non_null(current_inputs, incoming_inputs)

    updated_collected_data = dict(current_collected_data)
    updated_collected_data["inputs"] = merged_inputs

    name = normalized_args.get("name") or normalized_args.get("first_name") or chat_session.name
    phone = normalized_args.get("phone_number") or chat_session.phone
    if phone and isinstance(phone, str) and not phone.startswith("+91"):
        phone = f"+91{phone[-10:]}"

    lead_captured = bool((name or chat_session.name) and (phone or chat_session.phone))

    await db.execute(
        update(ChatSessions)
        .where(and_(ChatSessions.session_id == session_id, ChatSessions.thread_id == thread_id))
        .values(
            collected_data=updated_collected_data,
            name=name.capitalize() if isinstance(name, str) else name,
            phone=phone,
            lead_captured=lead_captured,
        )
    )
    await db.commit()
    return {"status": "success", "inputs": merged_inputs}


async def calculate_and_store_retirement_plan(
    db: AsyncSession,
    session_id: str,
    thread_id: str,
    function_args: dict,
):
    result = await db.execute(
        select(ChatSessions).where(
            and_(ChatSessions.session_id == session_id, ChatSessions.thread_id == thread_id)
        )
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        return {"status": "error", "message": "session_not_found"}

    normalized_args = _normalize_inputs(function_args)
    current_collected_data = chat_session.collected_data if isinstance(chat_session.collected_data, dict) else {}
    current_inputs = _extract_existing_inputs(current_collected_data)

    persisted_overrides = {k: normalized_args.get(k) for k in RETIREMENT_INPUT_KEYS if k in normalized_args}
    merged_inputs = _merge_non_null(current_inputs, persisted_overrides)

    calc_inputs = dict(merged_inputs)
    for key in (
        "annual_inflation_rate",
        "annual_return_rate",
        "corpus_multiplier_years",
        "scenario",
        "monthly_sip_override",
    ):
        if normalized_args.get(key) is not None:
            calc_inputs[key] = normalized_args.get(key)

    calculation = calculate_retirement_plan_payload(calc_inputs)

    updated_collected_data = dict(current_collected_data)
    updated_collected_data["inputs"] = merged_inputs
    updated_collected_data["calculation"] = {"latest": calculation}

    await db.execute(
        update(ChatSessions)
        .where(and_(ChatSessions.session_id == session_id, ChatSessions.thread_id == thread_id))
        .values(collected_data=updated_collected_data)
    )
    await db.commit()

    return calculation


async def get_chat_sessions_db(
    db: AsyncSession,
    limit: int | None = 10,
    offset: int | None = 0,
):
    result = await db.execute(
        select(ChatSessions)
        .where(ChatSessions.lead_captured == True)
        .order_by(ChatSessions.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
