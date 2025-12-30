def inject_initial_context(thread_id: str, goal: str, client):
    goal_map = {
        "retirement": "Retirement planning",
        "child_education": "Child education planning",
        "savings": "Savings with protection",
        "human_life_value": "Human Life Value assessment"
    }

    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="assistant",
        content=f"""
            The user has already selected the primary planning objective as:
            {goal_map.get(goal, goal)}.

            Do NOT ask the user to choose a planning goal again.
            Proceed with questions relevant to this objective only.
            """
    )
