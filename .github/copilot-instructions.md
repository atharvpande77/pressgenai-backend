# AI Development Guide for pressgenai-backend

This guide provides essential context for AI agents working with the pressgenai-backend codebase.

## Project Overview

PressGenAI is an AI-powered news generation platform built with FastAPI and SQLAlchemy. The system allows creators to:
- Generate and manage news stories based on location data
- Create user stories with specific metadata (tone, style, language)
- Generate contextual questions and answers
- Produce AI-written articles with controlled parameters

## Architecture

### Key Components
- `src/stories/` - Core story generation and management
- `src/creators/` - Author/creator profile management
- `src/auth/` - Authentication and role-based access control
- `src/models.py` - SQLAlchemy models
- `src/schemas.py` - Pydantic schemas for request/response validation

### Data Flow
1. User stories start as drafts with metadata (tone, style, etc.)
2. System generates contextual questions (5W1H + sources)
3. Creators provide answers to guide article generation
4. AI generates article based on answers and metadata
5. Stories move through states: draft → submitted → rejected/published

## Development Patterns

### FastAPI Routing Pattern
```python
@router.get(
    "/path",
    response_model=ResponseSchema,
    summary="Endpoint summary",
    description="""Detailed markdown
    description""",
    responses={
        404: {"description": "Error case"},
    }
)
```

### Database Access
- Use `AsyncSession` from SQLAlchemy for all DB operations
- Always get session via dependency: `session: Annotated[AsyncSession, Depends(get_session)]`
- Handle operations in service layer (`*/service.py` files)

### Authentication
- Role-based access via `@Depends(role_checker('role_name'))`
- Roles defined in `UserRoles` enum
- Author authentication handled in `src/auth/` module

### Error Handling
- Use FastAPI's `HTTPException` with appropriate status codes
- Catch specific exceptions and wrap in HTTP responses
- Include detailed error messages in development

## Common Workflows

### Story Generation Flow
1. Create user story with `/user` POST endpoint
2. Generate/fetch questions with `/user/{id}/questions`
3. Submit answers via `/user/{id}/answer`
4. Generate article using `/user/{id}/generate`
5. Submit for review with status update to "submitted"

### Development Setup
1. Requires Python 3.9+
2. Install dependencies: `pip install -r requirements.txt`
3. Set up database migrations: `alembic upgrade head`
4. Configure environment variables (see `.env.example`)

### Testing
- Test files located alongside implementation files
- Use async test clients for API testing
- Mock external services (AI generation, etc.)

## Key Integration Points

- External AI Service: Article generation and question creation
- AWS Integration: Media storage and processing
- Database: PostgreSQL with async SQLAlchemy
- Frontend: Expects specific response formats (see response models)

## Common Issues & Solutions

1. **Article Generation Failures**
   - Check AI service connectivity
   - Verify all required answers are provided
   - Ensure story metadata is complete

2. **Permission Errors**
   - Verify user role assignments
   - Check auth token expiration
   - Ensure correct role_checker dependency

3. **Database Operations**
   - Always use async/await with DB operations
   - Handle connection timeouts
   - Use appropriate transaction boundaries