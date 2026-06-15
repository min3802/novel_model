from .models import CoverImage, RelationshipMap


def cover_image_to_dict(image: CoverImage) -> dict:
    return {
        "id": image.id,
        "work_id": image.work_id,
        "target_country": image.target_country,
        "image_url": image.image_url or (image.image_file.url if image.image_file else ""),
        "is_representative": image.is_representative,
        "ai_notice": image.ai_notice,
        "created_at": image.created_at.isoformat() if image.created_at else None,
    }


def relationship_map_to_dict(relation_map: RelationshipMap, include_html: bool = False) -> dict:
    data = {
        "id": relation_map.id,
        "work_id": relation_map.work_id,
        "title": relation_map.title,
        "relation_data": relation_map.relation_data,
        "created_at": relation_map.created_at.isoformat() if relation_map.created_at else None,
    }
    if include_html:
        data["html_content"] = relation_map.html_content
    return data

