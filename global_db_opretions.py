from typing import Dict, Any, List, Optional, Tuple, Type, TypeVar
from beanie import Document, SortDirection
from pymongo import ReturnDocument
from beanie.odm.operators.update.general import Set  # ✅ Correct import
from pymongo.results import UpdateResult

T = TypeVar("T", bound=Document)


async def find(model: Type[T], find_obj: Dict[str, Any]) -> List[T]:
    query = {"isDeleted": False, **find_obj}
    return await model.find(query).to_list()



async def findWithSort(
    model: Type[T],
    find_obj: Dict[str, Any],
    sort_by: Optional[Tuple[str, Any]] = None
) -> List[T]:
    query = {"isDeleted": False, **find_obj}
    cursor = model.find(query)

    if sort_by:
        field, direction = sort_by
        # Convert int to SortDirection if needed
        if isinstance(direction, int):
            if direction == -1:
                direction = SortDirection.DESCENDING
            elif direction == 1:
                direction = SortDirection.ASCENDING
            else:
                raise ValueError("Invalid sort direction. Use 1 (asc) or -1 (desc)")

        # Apply sorting (as a list of tuples)
        cursor = cursor.sort([(field, direction)])  # ✅ expects list of tuple

    return await cursor.to_list()

async def find_one(model: Type[T], find_obj: Dict[str, Any]) -> Optional[T]:
    query = {"isDeleted": False, **find_obj}
    return await model.find_one(query)


async def update_one(
    model: Type[T],
    find_obj: Dict[str, Any],
    update_obj: Dict[str, Any],
    array_filters: list | None = None
) -> Optional[T]:
    try:
        query = {"isDeleted": False, **find_obj}

        # 🔹 Normal $set
        if "$set" in update_obj and not array_filters:
            await model.find_one(query).update(Set(update_obj["$set"]))

        # 🔹 Normal $push
        elif "$push" in update_obj:
            collection = model.get_pymongo_collection()
            await collection.update_one(query, update_obj)

        # 🔥 UUID based array update
        elif "$set" in update_obj and array_filters:
            collection = model.get_pymongo_collection()
            await collection.update_one(
                query,
                update_obj,
                array_filters=array_filters
            )

        else:
            raise ValueError("Unsupported update operation.")

        return await model.find_one(query)

    except Exception:
        import traceback
        print("Error occurred in update_one:")
        traceback.print_exc()


async def create(model: Type[T], data: dict) -> T:
    return await model(**data).insert()


async def update_many(
    model: Type[T],
    find_obj: Dict[str, Any],
    update_obj: Dict[str, Any]
) -> UpdateResult:
    query = {"isDeleted": False, **find_obj}
    
    # Only support $set for now
    if "$set" in update_obj:
        # Use model.get_collection() to access the Motor collection and run update_many
        result = await model.get_collection().update_many(query, {"$set": update_obj["$set"]})
    else:
        raise ValueError("Only '$set' updates are currently supported.")
    
    return result


async def insert_many(model: Type[T], insert_array: List[T]):
    return await model.insert_many(insert_array)


async def delete_many(model: Type[T], filter_obj: Dict[str, Any]):
    return await model.find(filter_obj).delete()


async def delete_one(model: Type[T], filter_obj: Dict[str, Any]):
    return await model.find_one(filter_obj).delete()


async def distinct(model: Type[T], field: str, find_obj: Dict[str, Any]) -> List[T]:
    query = {"isDeleted": False, **find_obj}
    return await model.distinct(field,query)