from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ..config import AppConfig
from ..errors import ParserError
from ..models import NormalizedShape, PageParseResult


def render_page(
    shapes: list[NormalizedShape],
    config: AppConfig,
    page_number: str,
    chapter: str,
) -> PageParseResult:
    descendants_by_ancestor = _build_descendants_index(shapes)
    text_cache = {
        shape.index: _render_text_with_marker_replacement(shape, shapes, config)
        for shape in shapes
    }
    caption_cache = {
        shape.index: _collect_caption(shape, shapes, config)
        for shape in shapes
    }
    marker_consumed = {
        child_index
        for _, consumed_indices in text_cache.values()
        for child_index in consumed_indices
    }
    caption_consumed = {
        child_index
        for _, consumed_indices in caption_cache.values()
        for child_index in consumed_indices
    }

    content_lines = []
    accounted_shape_indices: set[int] = set()
    for shape in shapes:
        if not _should_emit_in_page_contents(
            shape=shape,
            shapes=shapes,
            marker_consumed=marker_consumed,
            caption_consumed=caption_consumed,
        ):
            continue
        rendered, consumed_indices = _render_shape_in_context(
            shape=shape,
            config=config,
            text_cache=text_cache,
        )
        if rendered is not None:
            content_lines.append(rendered)
            accounted_shape_indices.add(shape.index)
            accounted_shape_indices.update(consumed_indices)

    add_info = []
    for shape in shapes:
        rule = config.label_rule(shape.label)
        if rule.use_in_contents != "tag":
            continue
        description, description_consumed = _build_description(
            shape=shape,
            shapes=shapes,
            config=config,
            text_cache=text_cache,
            marker_consumed=marker_consumed,
            caption_consumed=caption_consumed,
            descendants_by_ancestor=descendants_by_ancestor,
        )
        caption, caption_consumed_indices = caption_cache[shape.index]
        add_info.append(
            {
                "tag": shape.tag,
                "type": rule.type,
                "description": {
                    "value": description,
                },
                "caption": caption,
                "file_path": _build_file_path(shape, config),
            }
        )
        accounted_shape_indices.add(shape.index)
        accounted_shape_indices.update(description_consumed)
        accounted_shape_indices.update(caption_consumed_indices)

    _assert_child_tag_shapes_referenced(
        shapes=shapes,
        config=config,
        content_lines=content_lines,
        add_info=add_info,
    )
    _assert_all_shapes_accounted(shapes, accounted_shape_indices)

    return PageParseResult(
        page=page_number,
        chapter=chapter,
        page_contents="\n".join(content_lines),
        add_info=add_info,
    )


def first_title_on_page(shapes: list[NormalizedShape], config: AppConfig) -> str:
    for shape in shapes:
        rule = config.label_rule(shape.label)
        if rule.chapter_source and shape.flags_text:
            return shape.flags_text
    return ""


def _build_descendants_index(shapes: list[NormalizedShape]) -> dict[int, list[int]]:
    descendants_by_ancestor = {shape.index: [] for shape in shapes}
    for shape in shapes:
        for ancestor_index in shape.ancestor_indices:
            descendants_by_ancestor[ancestor_index].append(shape.index)
    return descendants_by_ancestor


def _render_shape_in_context(
    shape: NormalizedShape,
    config: AppConfig,
    text_cache: dict[int, tuple[str, set[int]]],
) -> tuple[Optional[str], set[int]]:
    rule = config.label_rule(shape.label)
    if rule.use_in_contents == "text":
        return text_cache[shape.index]
    if rule.use_in_contents == "tag":
        return _wrapped_tag(shape.tag), set()
    return None, set()


def _build_description(
    shape: NormalizedShape,
    shapes: list[NormalizedShape],
    config: AppConfig,
    text_cache: dict[int, tuple[str, set[int]]],
    marker_consumed: set[int],
    caption_consumed: set[int],
    descendants_by_ancestor: dict[int, list[int]],
) -> tuple[str, set[int]]:
    rule = config.label_rule(shape.label)
    if rule.description_mode == "children_rendered":
        return _render_children(
            parent=shape,
            shapes=shapes,
            config=config,
            text_cache=text_cache,
            marker_consumed=marker_consumed,
            caption_consumed=caption_consumed,
            descendants_by_ancestor=descendants_by_ancestor,
        )
    if rule.description_mode == "flags_text":
        return text_cache[shape.index]
    return "", set()


def _render_children(
    parent: NormalizedShape,
    shapes: list[NormalizedShape],
    config: AppConfig,
    text_cache: dict[int, tuple[str, set[int]]],
    marker_consumed: set[int],
    caption_consumed: set[int],
    descendants_by_ancestor: dict[int, list[int]],
) -> tuple[str, set[int]]:
    lines = []
    consumed_indices: set[int] = set()
    for child_index in descendants_by_ancestor[parent.index]:
        child = shapes[child_index]
        if not _should_emit_in_item_description(
            parent=parent,
            candidate=child,
            shapes=shapes,
            marker_consumed=marker_consumed,
            caption_consumed=caption_consumed,
        ):
            continue
        rendered, child_consumed = _render_shape_in_context(
            shape=child,
            config=config,
            text_cache=text_cache,
        )
        if rendered is not None:
            lines.append(rendered)
            consumed_indices.add(child.index)
            consumed_indices.update(child_consumed)
    return "\n".join(lines), consumed_indices


def _render_text_with_marker_replacement(
    shape: NormalizedShape,
    shapes: list[NormalizedShape],
    config: AppConfig,
) -> tuple[str, set[int]]:
    text = shape.flags_text
    if not text or not shape.children:
        return text, set()

    children_by_marker: defaultdict[str, list[NormalizedShape]] = defaultdict(list)
    for child_index in shape.children:
        child = shapes[child_index]
        child_rule = config.label_rule(child.label)
        if child_rule.marker:
            children_by_marker[child_rule.marker].append(child)

    updated_text = text
    consumed_indices: set[int] = set()
    for marker, children in children_by_marker.items():
        if updated_text.count(marker) != len(children):
            continue
        for child in children:
            updated_text = updated_text.replace(marker, _wrapped_tag(child.tag), 1)
            consumed_indices.add(child.index)
    return updated_text, consumed_indices


def _collect_caption(
    shape: NormalizedShape,
    shapes: list[NormalizedShape],
    config: AppConfig,
) -> tuple[str, set[int]]:
    rule = config.label_rule(shape.label)
    if rule.use_in_contents != "tag":
        return "", set()

    captions = []
    consumed_indices: set[int] = set()
    for child_index in shape.children:
        child = shapes[child_index]
        if child.label == "CAPTION" and child.flags_text:
            captions.append(child.flags_text)
            consumed_indices.add(child.index)
    return "\n".join(captions), consumed_indices


def _should_emit_in_page_contents(
    shape: NormalizedShape,
    shapes: list[NormalizedShape],
    marker_consumed: set[int],
    caption_consumed: set[int],
) -> bool:
    if shape.index in marker_consumed or shape.index in caption_consumed:
        return False
    if _has_ancestor_label(shape, shapes, "ITEM"):
        return False
    return True


def _should_emit_in_item_description(
    parent: NormalizedShape,
    candidate: NormalizedShape,
    shapes: list[NormalizedShape],
    marker_consumed: set[int],
    caption_consumed: set[int],
) -> bool:
    if candidate.index == parent.index:
        return False
    if candidate.index in marker_consumed or candidate.index in caption_consumed:
        return False
    if not _is_descendant_of(candidate, parent.index):
        return False
    if _has_intermediate_ancestor_label(candidate, parent.index, shapes, "ITEM"):
        return False
    return True


def _is_descendant_of(shape: NormalizedShape, ancestor_index: int) -> bool:
    return ancestor_index in shape.ancestor_indices


def _has_ancestor_label(shape: NormalizedShape, shapes: list[NormalizedShape], label: str) -> bool:
    return any(shapes[ancestor_index].label == label for ancestor_index in shape.ancestor_indices)


def _has_intermediate_ancestor_label(
    shape: NormalizedShape,
    ancestor_index: int,
    shapes: list[NormalizedShape],
    label: str,
) -> bool:
    for current_parent in shape.ancestor_indices:
        if current_parent == ancestor_index:
            return False
        if shapes[current_parent].label == label:
            return True
    return False


def _assert_all_shapes_accounted(shapes: list[NormalizedShape], accounted_shape_indices: set[int]) -> None:
    missing_shapes = [shape for shape in shapes if shape.index not in accounted_shape_indices]
    if not missing_shapes:
        return

    details = ", ".join(f"{shape.index}:{shape.label}" for shape in missing_shapes)
    raise ParserError(f"일부 shape가 contents/add_info에 반영되지 않았습니다: {details}")


def _assert_child_tag_shapes_referenced(
    shapes: list[NormalizedShape],
    config: AppConfig,
    content_lines: list[str],
    add_info: list[dict],
) -> None:
    rendered_targets = list(content_lines)
    rendered_targets.extend(
        info.get("description", {}).get("value", "")
        for info in add_info
    )

    unreferenced_shapes = []
    for shape in shapes:
        rule = config.label_rule(shape.label)
        if rule.use_in_contents != "tag":
            continue
        if shape.parent_index is None:
            continue
        if not shape.tag:
            continue
        wrapped_tag = _wrapped_tag(shape.tag)
        if any(wrapped_tag in target for target in rendered_targets):
            continue
        unreferenced_shapes.append(shape)

    if not unreferenced_shapes:
        return

    details = ", ".join(f"{shape.index}:{shape.label}" for shape in unreferenced_shapes)
    raise ParserError(f"일부 add_info tag가 contents/description에 참조되지 않았습니다: {details}")


def _build_file_path(shape: NormalizedShape, config: AppConfig) -> str:
    rule = config.label_rule(shape.label)
    if not rule.crop:
        return ""
    return config.parser.crop_dir_template.format(label=shape.label) + f"/{shape.tag}.png"


def _wrapped_tag(tag: str) -> str:
    return f"{{{tag}}}"
