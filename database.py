from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from models.company import Company
from models.project import Project
import os
from dotenv import load_dotenv
import certifi

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")

async def init_db():
    client = AsyncIOMotorClient(
        MONGODB_URL,
        tlsCAFile=certifi.where()
    )
    database = client.websiteAeo
    
    await init_beanie(
        database=database,
        document_models=[Company, Project]
    )
    
    print("Connected to MongoDB successfully!")