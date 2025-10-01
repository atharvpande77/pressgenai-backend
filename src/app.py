from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socket

from src.stories.router import router as stories_router
from src.editor.router import router as editor_router
from src.creators.router import router as authors_router
from src.auth.router import router as auth_router
from src.admin.router import router as admin_router
from src.news.router import router as news_router

app = FastAPI(
    root_path='/pressgenai',
    title="Pressgen.ai Backend APIs",
    version="0.0.1",
    description="""
        Pressgen.ai is an AI-powered SaaS that helps users generate structured news-style 
        articles from context and Q&A inputs.  

        This API provides endpoints to:  
        - Create and manage user stories  
        - Generate contextual questions for stories  
        - Submit and update answers  
        - Generate AI-written articles with tone, style, and length preferences  

        The backend is built with FastAPI and uses async SQLAlchemy sessions for database interactions.
        """
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# templates = Jinja2Templates(directory="src/templates")

# app.mount("/static", StaticFiles(directory="src/static", html=True), name="static")

app.include_router(stories_router, prefix="/api/stories", tags=["stories"])
app.include_router(editor_router, prefix="/api/editor", tags=["editor"])
app.include_router(authors_router, prefix="/api/creator", tags=["creator"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(news_router, prefix="/api/news", tags=["news"])

hostname = socket.gethostname()
IPAddr = socket.gethostbyname(hostname)

@app.get("/")
async def root():
    # return templates.TemplateResponse("index.html", { "request": {} })
    # return FileResponse("src/static/index.html")
    return {"status": "ok", "local_hostname": hostname, "local_ip": IPAddr}