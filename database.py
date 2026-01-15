import os
import pkgutil
import importlib
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from beanie import init_beanie, Document
import certifi

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_NAME = os.getenv("MONGODB_NAME", "websiteAeo")  # database name

try:
    client = AsyncIOMotorClient(
        MONGODB_URL,
        tlsCAFile=certifi.where()  # ensures SSL cert validation
    )
    db = client[MONGODB_NAME]
    print("Successfully connected to MongoDB!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    client = None
    db = None

async def load_beanie_models(models_package_name: str = "models"):
    """
    Dynamically loads all Beanie Document models from the given package
    """
    models_package = importlib.import_module(models_package_name)
    model_classes = []

    for _, module_name, _ in pkgutil.iter_modules(models_package.__path__):
        module = importlib.import_module(f"{models_package_name}.{module_name}")
        for attr in dir(module):
            value = getattr(module, attr)
            try:
                if isinstance(value, type) and issubclass(value, Document) and value is not Document:
                    model_classes.append(value)
            except TypeError:
                continue

    return model_classes

async def init_db(models_package_name: str = "models"):
    """
    Initializes Beanie with all models in the given package
    """
    if client is None:
        raise RuntimeError("MongoDB client not initialized")

    model_classes = await load_beanie_models(models_package_name)
    await init_beanie(
        database=db,
        document_models=model_classes,
    )
    print("Beanie initialized with models:", [m.__name__ for m in model_classes])
