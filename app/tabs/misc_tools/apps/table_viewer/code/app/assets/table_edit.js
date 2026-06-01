// 표 편집용 JavaScript — 셀 추적 + 행/열 추가·삭제 + 병합/분할 + 클립보드 + 정합성 체크
(function () {
  // ===== 상태 =====
  let selected = new Set();   // 선택된 셀 DOM 집합
  let anchor = null;          // shift 범위 선택의 기준 셀
  let last = null;            // 가장 최근 클릭된 셀(작업 기준)
  let clipboard = null;       // {cells: [innerHTML,...], rows, cols}
  let dragStart = null;       // mousedown된 셀 (잠재적 드래그 시작)
  let cellDragMode = false;   // 실제로 셀 드래그가 시작되었는지
  let textEditCell = null;    // 실제 텍스트 편집 중인 단일 셀
  let selectionPopup = null;  // 선택 셀 근처에 뜨는 액션 팝업
  let popupUpdateQueued = false;
  let popupDragState = null;
  let textEditBaseSnapshot = null;
  let undoStack = [];
  let currentSnapshot = null;
  let tableDirty = false;
  let drawSplitState = null;    // 선택 셀 내부 분할선 그리기 모드 상태
  const POPUP_STORAGE_KEY = '__tableViewerSelectionPopupPosition';
  const UNDO_LIMIT = 5;
  // 편집 도구는 PyQt 좌측 탭에서 제공해 표 영역을 가리지 않게 한다.
  const POPUP_ENABLED = false;
  let popupManualPosition = loadPopupPosition();

  // ===== 그리드 매핑 =====
  function buildGrid(table) {
    const rows = Array.from(table.rows);
    const grid = [];
    for (let r = 0; r < rows.length; r++) {
      grid[r] = grid[r] || [];
      let c = 0;
      for (const cell of rows[r].cells) {
        while (grid[r][c]) c++;
        const rs = cell.rowSpan || 1, cs = cell.colSpan || 1;
        for (let i = 0; i < rs; i++) for (let j = 0; j < cs; j++) {
          grid[r + i] = grid[r + i] || [];
          grid[r + i][c + j] = cell;
        }
        c += cs;
      }
    }
    return { rows, grid };
  }
  function findCellPos(table, cell) {
    const { grid } = buildGrid(table);
    for (let r = 0; r < grid.length; r++) {
      const row = grid[r] || [];
      for (let c = 0; c < row.length; c++) if (row[c] === cell) return { r, c, grid };
    }
    return null;
  }
  function colCount(table) {
    const { grid } = buildGrid(table);
    return Math.max(...grid.map(r => r ? r.length : 0));
  }
  function newCell(tagName) {
    const el = document.createElement(tagName || 'td');
    return el;
  }
  function isBlankCell(cell) {
    if (!cell) return false;
    const text = (cell.textContent || '').replace(/\u00a0/g, '').trim();
    if (text) return false;
    return Array.from(cell.childNodes).every(node => (
      node.nodeType === Node.TEXT_NODE ||
      (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'BR')
    ));
  }
  function clearBlankCellPlaceholder(cell) {
    if (isBlankCell(cell)) cell.innerHTML = '';
  }
  function normalizeCellSpanAttrs(cell) {
    if (!cell || !cell.getAttribute) return;
    if ((cell.rowSpan || 1) <= 1 || cell.getAttribute('rowspan') === '1') {
      cell.removeAttribute('rowspan');
    }
    if ((cell.colSpan || 1) <= 1 || cell.getAttribute('colspan') === '1') {
      cell.removeAttribute('colspan');
    }
  }
  function activeTable() {
    return last ? last.closest('table') : null;
  }
  function editableRoot() {
    return document.getElementById('editable');
  }
  function isMarkdownMode() {
    const root = editableRoot();
    return !!root && root.dataset.tableFormat === 'markdown';
  }
  function clearNativeSelection() {
    const sel = window.getSelection();
    if (sel) sel.removeAllRanges();
  }
  function isSingleSelectedCell(cell) {
    return selected.size === 1 && selected.has(cell) && last === cell;
  }
  function markDirty() {
    tableDirty = true;
  }
  function cleanRuntimeMarkup(root) {
    if (!root) return;
    const runtimeNodes = root.querySelectorAll('.__sel, .__editing, .__short, .__drawTarget, [contenteditable]');
    runtimeNodes.forEach(node => {
      node.classList.remove('__sel', '__editing', '__short', '__drawTarget');
      if (node.getAttribute('class') === '') node.removeAttribute('class');
      node.removeAttribute('contenteditable');
    });
    if (root.getAttribute && root.getAttribute('class') === '') root.removeAttribute('class');
    root.querySelectorAll('[class=""]').forEach(node => node.removeAttribute('class'));
    root.querySelectorAll('td,th').forEach(cell => {
      clearBlankCellPlaceholder(cell);
      normalizeCellSpanAttrs(cell);
    });
  }
  function sanitizedHtmlFrom(root) {
    if (!root) return null;
    const clone = root.cloneNode(true);
    cleanRuntimeMarkup(clone);
    return clone.innerHTML;
  }
  function sanitizeHtmlString(html) {
    if (html === null) return null;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    cleanRuntimeMarkup(wrapper);
    return wrapper.innerHTML;
  }
  function snapshotHtml() {
    const editable = editableRoot();
    return editable ? sanitizedHtmlFrom(editable) : null;
  }
  function peekEditableHtml() {
    const editable = editableRoot();
    return editable ? sanitizedHtmlFrom(editable) : null;
  }
  function consumeDirtyHtml() {
    if (!tableDirty) return null;
    tableDirty = false;
    return peekEditableHtml();
  }
  function resetCurrentSnapshot() {
    currentSnapshot = snapshotHtml();
    tableDirty = false;
  }
  function pushUndoSnapshot(snapshot) {
    if (snapshot === null) return;
    if (undoStack.length && undoStack[undoStack.length - 1] === snapshot) return;
    undoStack.push(snapshot);
    if (undoStack.length > UNDO_LIMIT) undoStack.shift();
  }
  function rememberSnapshot(beforeHtml) {
    const afterHtml = snapshotHtml();
    if (beforeHtml === null || afterHtml === null) {
      currentSnapshot = afterHtml;
      return false;
    }
    if (beforeHtml === afterHtml) {
      currentSnapshot = afterHtml;
      return false;
    }
    pushUndoSnapshot(beforeHtml);
    currentSnapshot = afterHtml;
    markDirty();
    return true;
  }
  function commitTextEditSnapshot() {
    const beforeHtml = textEditBaseSnapshot;
    textEditBaseSnapshot = null;
    if (beforeHtml !== null) rememberSnapshot(beforeHtml);
  }
  function exitTextEditMode(captureSnapshot) {
    if (!textEditCell) return;
    if (captureSnapshot === undefined) captureSnapshot = true;
    textEditCell.removeAttribute('contenteditable');
    textEditCell.classList.remove('__editing');
    if (document.activeElement === textEditCell && typeof textEditCell.blur === 'function') {
      textEditCell.blur();
    }
    textEditCell = null;
    if (captureSnapshot) commitTextEditSnapshot();
    else textEditBaseSnapshot = null;
    schedulePopupUpdate();
  }
  function enterTextEditMode(cell) {
    if (!cell) return;
    if (textEditCell !== cell) exitTextEditMode();
    textEditCell = cell;
    textEditBaseSnapshot = snapshotHtml();
    clearBlankCellPlaceholder(textEditCell);
    textEditCell.setAttribute('contenteditable', 'true');
    textEditCell.classList.add('__editing');
    schedulePopupUpdate();
  }
  function focusTextEditCell(cell, placement) {
    if (!cell) return;
    try {
      cell.focus({ preventScroll: true });
    } catch (_err) {
      cell.focus();
    }
    const sel = window.getSelection();
    if (!sel) return;
    const range = document.createRange();
    range.selectNodeContents(cell);
    if (placement !== 'all') range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }
  function insertTextAtCaret(text) {
    if (text === '') return;
    const ok = document.execCommand && document.execCommand('insertText', false, text);
    if (ok) return;
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) {
      if (textEditCell) textEditCell.textContent = (textEditCell.textContent || '') + text;
      markDirty();
      return;
    }
    const range = sel.getRangeAt(0);
    range.deleteContents();
    const node = document.createTextNode(text);
    range.insertNode(node);
    range.setStartAfter(node);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    markDirty();
  }
  function insertLineBreakAtCaret() {
    const ok = document.execCommand && document.execCommand('insertLineBreak', false, null);
    if (ok) {
      markDirty();
      return;
    }
    if (document.execCommand && document.execCommand('insertHTML', false, '<br>')) {
      markDirty();
      return;
    }
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    range.deleteContents();
    const br = document.createElement('br');
    range.insertNode(br);
    range.setStartAfter(br);
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);
    markDirty();
  }
  function selectedEditableCell() {
    if (!last) return null;
    if (selected.size === 0) return last;
    return selected.size === 1 && selected.has(last) ? last : null;
  }
  function isDirectTextKey(e) {
    return (
      e.key &&
      e.key.length === 1 &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey
    );
  }
  function beginKeyboardTextEdit(cell, initialText) {
    if (!cell) return;
    enterTextEditMode(cell);
    if (initialText !== undefined) {
      cell.innerHTML = '';
      focusTextEditCell(cell, 'end');
      insertTextAtCaret(initialText);
      markDirty();
      return;
    }
    focusTextEditCell(cell, 'end');
  }
  function selectCellAfterTextEdit(cell) {
    const fallback = textEditCell;
    exitTextEditMode();
    clearNativeSelection();
    selectOne(cell || fallback);
  }
  function cellBelow(cell) {
    if (!cell) return null;
    const table = cell.closest('table');
    if (!table) return null;
    const pos = findCellPos(table, cell);
    if (!pos) return null;
    const row = pos.r + (cell.rowSpan || 1);
    return pos.grid[row] ? (pos.grid[row][pos.c] || null) : null;
  }
  function cellAbove(cell) {
    if (!cell) return null;
    const table = cell.closest('table');
    if (!table) return null;
    const pos = findCellPos(table, cell);
    if (!pos || pos.r <= 0) return null;
    return pos.grid[pos.r - 1] ? (pos.grid[pos.r - 1][pos.c] || null) : null;
  }
  function cellRight(cell) {
    if (!cell) return null;
    const table = cell.closest('table');
    if (!table) return null;
    const pos = findCellPos(table, cell);
    if (!pos) return null;
    return pos.grid[pos.r] ? (pos.grid[pos.r][pos.c + (cell.colSpan || 1)] || null) : null;
  }
  function cellLeft(cell) {
    if (!cell) return null;
    const table = cell.closest('table');
    if (!table) return null;
    const pos = findCellPos(table, cell);
    if (!pos || pos.c <= 0) return null;
    return pos.grid[pos.r] ? (pos.grid[pos.r][pos.c - 1] || null) : null;
  }
  function cellByArrowKey(cell, key) {
    if (key === 'ArrowUp') return cellAbove(cell);
    if (key === 'ArrowDown') return cellBelow(cell);
    if (key === 'ArrowLeft') return cellLeft(cell);
    if (key === 'ArrowRight') return cellRight(cell);
    return null;
  }
  function nextCell(cell) {
    if (!cell) return null;
    const table = cell.closest('table');
    if (!table) return null;
    const all = Array.from(table.querySelectorAll('td,th'));
    const idx = all.indexOf(cell);
    return idx >= 0 && idx + 1 < all.length ? all[idx + 1] : null;
  }
  function currentEditableHtml() {
    exitTextEditMode();
    tableDirty = false;
    const editable = editableRoot();
    return editable ? sanitizedHtmlFrom(editable) : null;
  }
  function schedulePopupUpdate() {
    if (popupUpdateQueued) return;
    popupUpdateQueued = true;
    window.requestAnimationFrame(function () {
      popupUpdateQueued = false;
      updateSelectionPopup();
    });
  }
  function loadPopupPosition() {
    try {
      const raw = window.localStorage.getItem(POPUP_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || !Number.isFinite(parsed.left) || !Number.isFinite(parsed.top)) {
        return null;
      }
      return { left: parsed.left, top: parsed.top };
    } catch (_err) {
      return null;
    }
  }
  function savePopupPosition(left, top) {
    popupManualPosition = { left: Math.round(left), top: Math.round(top) };
    try {
      window.localStorage.setItem(
        POPUP_STORAGE_KEY,
        JSON.stringify(popupManualPosition)
      );
    } catch (_err) {
      // localStorage 미지원 환경에서는 메모리 상태만 유지한다.
    }
  }
  function clampPopupPosition(left, top, width, height) {
    const maxLeft = Math.max(8, window.innerWidth - width - 8);
    const maxTop = Math.max(8, window.innerHeight - height - 8);
    return {
      left: Math.min(Math.max(8, left), maxLeft),
      top: Math.min(Math.max(8, top), maxTop),
    };
  }
  function applyPopupPosition(left, top, width, height, persist) {
    if (!selectionPopup) return;
    const clamped = clampPopupPosition(left, top, width, height);
    selectionPopup.style.left = `${clamped.left}px`;
    selectionPopup.style.top = `${clamped.top}px`;
    if (persist) savePopupPosition(clamped.left, clamped.top);
  }
  function beginPopupDrag(e) {
    if (e.button !== 0 || !selectionPopup) return;
    const rect = selectionPopup.getBoundingClientRect();
    popupDragState = {
      dx: e.clientX - rect.left,
      dy: e.clientY - rect.top,
    };
    document.addEventListener('mousemove', onPopupDrag, true);
    document.addEventListener('mouseup', endPopupDrag, true);
    e.preventDefault();
    e.stopPropagation();
  }
  function onPopupDrag(e) {
    if (!popupDragState || !selectionPopup) return;
    const rect = selectionPopup.getBoundingClientRect();
    applyPopupPosition(
      e.clientX - popupDragState.dx,
      e.clientY - popupDragState.dy,
      rect.width,
      rect.height,
      false
    );
    e.preventDefault();
  }
  function endPopupDrag(e) {
    if (!popupDragState || !selectionPopup) return;
    const rect = selectionPopup.getBoundingClientRect();
    applyPopupPosition(rect.left, rect.top, rect.width, rect.height, true);
    popupDragState = null;
    document.removeEventListener('mousemove', onPopupDrag, true);
    document.removeEventListener('mouseup', endPopupDrag, true);
    if (e) e.preventDefault();
  }
  function clearSelectionState() {
    clearSelection();
    anchor = null;
    last = null;
  }
  function restoreSnapshot(snapshot) {
    const editable = editableRoot();
    if (!editable || snapshot === null) return false;
    const cleanedSnapshot = sanitizeHtmlString(snapshot);
    exitTextEditMode(false);
    clearSelectionState();
    clearNativeSelection();
    editable.innerHTML = cleanedSnapshot;
    currentSnapshot = cleanedSnapshot;
    markDirty();
    schedulePopupUpdate();
    return true;
  }
  function undoLastAction() {
    if (!undoStack.length) return false;
    return restoreSnapshot(undoStack.pop());
  }

  // ===== 선택 관리 =====
  function clearSelection() {
    selected.forEach(c => c.classList.remove('__sel'));
    selected.clear();
    const root = editableRoot();
    if (root) {
      root.querySelectorAll('.__sel').forEach(c => c.classList.remove('__sel'));
    }
    schedulePopupUpdate();
  }
  function selectOne(cell) {
    clearSelection();
    selected.add(cell);
    cell.classList.add('__sel');
    anchor = cell;
    last = cell;
    schedulePopupUpdate();
  }
  function toggleOne(cell) {
    if (selected.has(cell)) {
      selected.delete(cell);
      cell.classList.remove('__sel');
    } else {
      selected.add(cell);
      cell.classList.add('__sel');
    }
    last = cell;
    schedulePopupUpdate();
  }
  function selectRange(a, b) {
    const table = a.closest('table');
    if (!table || b.closest('table') !== table) return;
    const pa = findCellPos(table, a), pb = findCellPos(table, b);
    if (!pa || !pb) return;
    const r1 = Math.min(pa.r, pb.r), r2 = Math.max(pa.r, pb.r);
    const c1 = Math.min(pa.c, pb.c), c2 = Math.max(pa.c, pb.c);
    const { grid } = buildGrid(table);
    clearSelection();
    for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) {
      const cell = grid[r] && grid[r][c];
      if (cell && !selected.has(cell)) {
        selected.add(cell);
        cell.classList.add('__sel');
      }
    }
    last = b;
    schedulePopupUpdate();
  }
  function selectedInDOMOrder() {
    if (selected.size === 0) return [];
    const table = [...selected][0].closest('table');
    const all = Array.from(table.querySelectorAll('td,th'));
    return all.filter(c => selected.has(c));
  }
  function selectionRect() {
    if (selected.size === 0) return null;
    const table = [...selected][0].closest('table');
    const { grid } = buildGrid(table);
    let r1 = Infinity, c1 = Infinity, r2 = -1, c2 = -1;
    for (let r = 0; r < grid.length; r++) {
      const row = grid[r] || [];
      for (let c = 0; c < row.length; c++) {
        if (selected.has(row[c])) {
          if (r < r1) r1 = r; if (c < c1) c1 = c;
          if (r > r2) r2 = r; if (c > c2) c2 = c;
        }
      }
    }
    return { table, r1, c1, r2, c2, grid };
  }
  function selectionBounds() {
    const cells = selectedInDOMOrder();
    if (!cells.length) return null;
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    cells.forEach(cell => {
      const rect = cell.getBoundingClientRect();
      left = Math.min(left, rect.left);
      top = Math.min(top, rect.top);
      right = Math.max(right, rect.right);
      bottom = Math.max(bottom, rect.bottom);
    });
    return { left, top, right, bottom };
  }
  function hasSplitTarget() {
    const targets = selectedInDOMOrder();
    if (targets.some(c => (c.colSpan || 1) > 1 || (c.rowSpan || 1) > 1)) return true;
    return !!last && ((last.colSpan || 1) > 1 || (last.rowSpan || 1) > 1);
  }
  function hasActiveSelection() {
    return selected.size > 0 || !!last;
  }

  // ===== 선택 팝업 =====
  const popupGroups = [
    { key: 'row', title: '행' },
    { key: 'col', title: '열' },
    { key: 'cell', title: '셀' },
    { key: 'edit', title: '편집' },
    { key: 'section', title: '헤더 / 하단' },
    { key: 'normalize', title: '정합' },
  ];
  const popupOps = [
    { group: 'row', label: '위 추가', title: '위에 행 추가', op: 'addRowAbove', enabled: () => !!last },
    { group: 'row', label: '아래 추가', title: '아래에 행 추가', op: 'addRowBelow', enabled: () => !!last },
    { group: 'row', label: '행 삭제', title: '선택 행 삭제', op: 'delRow', enabled: () => hasActiveSelection() },
    { group: 'col', label: '왼쪽 추가', title: '왼쪽 열 추가', op: 'addColLeft', enabled: () => !!last },
    { group: 'col', label: '오른쪽 추가', title: '오른쪽 열 추가', op: 'addColRight', enabled: () => !!last },
    { group: 'col', label: '열 삭제', title: '선택 열 삭제', op: 'delCol', enabled: () => hasActiveSelection() },
    { group: 'cell', label: '병합', title: '선택 셀 병합', op: 'mergeSelection', show: () => selected.size > 1, enabled: () => selected.size > 1 },
    { group: 'cell', label: '분할', title: '병합 셀 분할', op: 'splitCell', show: () => hasSplitTarget(), enabled: () => hasSplitTarget() },
    { group: 'cell', label: '셀 추가', title: '현재 행 끝에 셀 추가', op: 'addCellEnd', enabled: () => !!last },
    { group: 'edit', label: '잘라내기', title: '선택 셀 잘라내기', op: 'cut', enabled: () => selected.size > 0 },
    { group: 'edit', label: '복사', title: '선택 셀 복사', op: 'copy', enabled: () => selected.size > 0 },
    { group: 'edit', label: '붙여넣기', title: '선택 셀 붙여넣기', op: 'paste', enabled: () => !!clipboard && selected.size > 0 && selected.size === clipboard.count },
    { group: 'section', label: '헤더 지정', title: '헤더 지정', op: 'setHeader', show: () => !isMarkdownMode(), enabled: () => hasActiveSelection() },
    { group: 'section', label: '헤더 해제', title: '헤더 해제', op: 'unsetHeader', show: () => !isMarkdownMode(), enabled: () => hasActiveSelection() },
    { group: 'section', label: '하단 지정', title: 'tfoot 지정', op: 'setFooter', show: () => !isMarkdownMode(), enabled: () => hasActiveSelection() },
    { group: 'section', label: '하단 해제', title: 'tfoot 해제', op: 'unsetFooter', show: () => !isMarkdownMode(), enabled: () => hasActiveSelection() },
    { group: 'normalize', label: '열 맞춤', title: '전체 행 열 수 정규화', op: 'normalizeTable', enabled: () => !!last },
  ];

  function ensureSelectionPopup() {
    if (selectionPopup) return selectionPopup;
    const popup = document.createElement('div');
    popup.id = '__selectionPopup';
    popup.hidden = true;
    popup.addEventListener('mousedown', function (e) {
      e.stopPropagation();
    }, true);
    popup.addEventListener('click', function (e) {
      const btn = e.target.closest('button[data-op]');
      if (!btn || btn.disabled) return;
      e.preventDefault();
      e.stopPropagation();
      window.__tableOp(btn.dataset.op);
    });
    const header = document.createElement('div');
    header.className = '__popupHeader';
    header.textContent = '편집 도구';
    header.addEventListener('mousedown', beginPopupDrag, true);
    popup.appendChild(header);
    popupGroups.forEach(groupCfg => {
      const section = document.createElement('section');
      section.className = '__popupSection';
      section.dataset.group = groupCfg.key;

      const title = document.createElement('div');
      title.className = '__popupSectionTitle';
      title.textContent = groupCfg.title;
      section.appendChild(title);

      const actions = document.createElement('div');
      actions.className = '__popupActions';
      popupOps
        .filter(cfg => cfg.group === groupCfg.key)
        .forEach(cfg => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.dataset.op = cfg.op;
          btn.dataset.label = cfg.label;
          btn.textContent = cfg.label;
          btn.title = cfg.title || cfg.label;
          actions.appendChild(btn);
        });
      section.appendChild(actions);
      popup.appendChild(section);
    });
    document.body.appendChild(popup);
    selectionPopup = popup;
    return popup;
  }

  function updateSelectionPopup() {
    if (!POPUP_ENABLED) {
      if (selectionPopup) selectionPopup.hidden = true;
      return;
    }
    const popup = ensureSelectionPopup();
    if (!editableRoot() || textEditCell || selected.size === 0) {
      popup.hidden = true;
      return;
    }
    const bounds = selectionBounds();
    if (!bounds) {
      popup.hidden = true;
      return;
    }

    const buttons = Array.from(popup.querySelectorAll('button[data-op]'));
    buttons.forEach(btn => {
      const cfg = popupOps.find(item => item.op === btn.dataset.op);
      if (!cfg) return;
      const visible = cfg.show ? cfg.show() : true;
      btn.hidden = !visible;
      btn.disabled = !visible || (cfg.enabled ? !cfg.enabled() : false);
    });
    Array.from(popup.querySelectorAll('[data-group]')).forEach(section => {
      const hasVisibleButton = Array.from(section.querySelectorAll('button[data-op]'))
        .some(btn => !btn.hidden);
      section.hidden = !hasVisibleButton;
    });

    popup.hidden = false;
    const rect = popup.getBoundingClientRect();
    if (popupDragState) return;
    if (popupManualPosition) {
      applyPopupPosition(
        popupManualPosition.left,
        popupManualPosition.top,
        rect.width,
        rect.height,
        false
      );
      return;
    }
    let left = bounds.left + (bounds.right - bounds.left - rect.width) / 2;
    let top = bounds.top - rect.height - 10;
    if (top < 8) {
      top = bounds.bottom + 10;
    }
    applyPopupPosition(left, top, rect.width, rect.height, false);
  }

  // ===== 분할선 그리기 모드 =====
  function drawTargetCell() {
    const selectedCell = selectedEditableCell();
    return selectedCell || last;
  }
  function uniqueSorted(values, maxValue) {
    const eps = 2;
    const out = [0, maxValue];
    values.forEach(value => {
      const clamped = Math.max(0, Math.min(maxValue, value));
      if (clamped <= eps || clamped >= maxValue - eps) return;
      if (!out.some(existing => Math.abs(existing - clamped) <= eps)) out.push(clamped);
    });
    return out.sort((a, b) => a - b);
  }
  function snapCoord(value, coords, threshold) {
    for (const coord of coords) {
      if (Math.abs(value - coord) <= threshold) return coord;
    }
    return value;
  }
  function axisLineElement(line) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    el.setAttribute('x1', line.x1);
    el.setAttribute('y1', line.y1);
    el.setAttribute('x2', line.x2);
    el.setAttribute('y2', line.y2);
    el.setAttribute('class', '__drawLine');
    return el;
  }
  function removeDrawSplitOverlay() {
    if (!drawSplitState) return;
    if (drawSplitState.target) drawSplitState.target.classList.remove('__drawTarget');
    if (drawSplitState.overlay) drawSplitState.overlay.remove();
    window.removeEventListener('scroll', positionDrawSplitOverlay, true);
    window.removeEventListener('resize', positionDrawSplitOverlay);
    drawSplitState = null;
  }
  function positionDrawSplitOverlay() {
    if (!drawSplitState || !drawSplitState.target || !drawSplitState.overlay) return;
    const rect = drawSplitState.target.getBoundingClientRect();
    drawSplitState.rect = rect;
    drawSplitState.overlay.style.left = `${rect.left}px`;
    drawSplitState.overlay.style.top = `${rect.top}px`;
    drawSplitState.overlay.style.width = `${rect.width}px`;
    drawSplitState.overlay.style.height = `${rect.height}px`;
    drawSplitState.svg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
  }
  function drawLineSnapCoords(axis) {
    if (!drawSplitState) return [];
    const rect = drawSplitState.rect;
    const base = axis === 'x' ? [0, rect.width] : [0, rect.height];
    drawSplitState.lines.forEach(line => {
      if (axis === 'x' && line.axis === 'v') base.push(line.x1);
      if (axis === 'y' && line.axis === 'h') base.push(line.y1);
    });
    return base;
  }
  function renderDrawSplitLines() {
    if (!drawSplitState || !drawSplitState.svg) return;
    drawSplitState.svg.innerHTML = '';
    drawSplitState.lines.forEach(line => drawSplitState.svg.appendChild(axisLineElement(line)));
    if (drawSplitState.draft) {
      const draft = axisLineElement(drawSplitState.draft);
      draft.setAttribute('class', '__drawLine __draft');
      drawSplitState.svg.appendChild(draft);
    }
  }
  function makeDrawLine(start, end, rect) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const axis = Math.abs(dx) >= Math.abs(dy) ? 'h' : 'v';
    const minLength = 10;
    const snap = 28;
    if (axis === 'h') {
      let x1 = Math.max(0, Math.min(rect.width, start.x));
      let x2 = Math.max(0, Math.min(rect.width, end.x));
      let y = Math.max(0, Math.min(rect.height, (start.y + end.y) / 2));
      if (Math.abs(x2 - x1) < minLength) return null;
      if (x2 < x1) [x1, x2] = [x2, x1];
      x1 = snapCoord(x1, drawLineSnapCoords('x'), snap);
      x2 = snapCoord(x2, drawLineSnapCoords('x'), snap);
      y = snapCoord(y, drawLineSnapCoords('y'), snap);
      if (Math.abs(x2 - x1) < minLength || y <= 1 || y >= rect.height - 1) return null;
      return { axis, x1, y1: y, x2, y2: y };
    }
    let y1 = Math.max(0, Math.min(rect.height, start.y));
    let y2 = Math.max(0, Math.min(rect.height, end.y));
    let x = Math.max(0, Math.min(rect.width, (start.x + end.x) / 2));
    if (Math.abs(y2 - y1) < minLength) return null;
    if (y2 < y1) [y1, y2] = [y2, y1];
    y1 = snapCoord(y1, drawLineSnapCoords('y'), snap);
    y2 = snapCoord(y2, drawLineSnapCoords('y'), snap);
    x = snapCoord(x, drawLineSnapCoords('x'), snap);
    if (Math.abs(y2 - y1) < minLength || x <= 1 || x >= rect.width - 1) return null;
    return { axis, x1: x, y1, x2: x, y2 };
  }
  function drawSplitLocalPoint(e) {
    const rect = drawSplitState.rect;
    return {
      x: Math.max(0, Math.min(rect.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, e.clientY - rect.top)),
    };
  }
  function beginDrawSplitDrag(e) {
    if (!drawSplitState || e.button !== 0 || e.target.closest('button')) return;
    drawSplitState.start = drawSplitLocalPoint(e);
    drawSplitState.draft = null;
    e.preventDefault();
    e.stopPropagation();
  }
  function moveDrawSplitDrag(e) {
    if (!drawSplitState || !drawSplitState.start) return;
    drawSplitState.draft = makeDrawLine(drawSplitState.start, drawSplitLocalPoint(e), drawSplitState.rect);
    renderDrawSplitLines();
    e.preventDefault();
    e.stopPropagation();
  }
  function endDrawSplitDrag(e) {
    if (!drawSplitState || !drawSplitState.start) return;
    const line = makeDrawLine(drawSplitState.start, drawSplitLocalPoint(e), drawSplitState.rect);
    drawSplitState.start = null;
    drawSplitState.draft = null;
    if (line) drawSplitState.lines.push(line);
    renderDrawSplitLines();
    e.preventDefault();
    e.stopPropagation();
  }
  function createDrawSplitToolbar(overlay) {
    const toolbar = document.createElement('div');
    toolbar.className = '__drawToolbar';
    const hint = document.createElement('span');
    hint.textContent = '수평/수직선만 입력됩니다';
    toolbar.appendChild(hint);
    [
      ['적용', applyDrawSplit],
      ['되돌리기', undoDrawSplitLine],
      ['취소', removeDrawSplitOverlay],
    ].forEach(([label, handler]) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = label;
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        handler();
      });
      toolbar.appendChild(btn);
    });
    overlay.appendChild(toolbar);
  }
  function enterDrawSplitMode() {
    const target = drawTargetCell();
    if (!target) {
      alert('분할할 셀을 먼저 선택하세요.');
      return;
    }
    removeDrawSplitOverlay();
    exitTextEditMode();
    clearNativeSelection();
    selectOne(target);
    target.classList.add('__drawTarget');
    const overlay = document.createElement('div');
    overlay.id = '__drawSplitOverlay';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('__drawSvg');
    overlay.appendChild(svg);
    createDrawSplitToolbar(overlay);
    overlay.addEventListener('mousedown', beginDrawSplitDrag, true);
    overlay.addEventListener('mousemove', moveDrawSplitDrag, true);
    overlay.addEventListener('mouseup', endDrawSplitDrag, true);
    document.body.appendChild(overlay);
    drawSplitState = { target, overlay, svg, lines: [], start: null, draft: null, rect: null };
    positionDrawSplitOverlay();
    window.addEventListener('scroll', positionDrawSplitOverlay, true);
    window.addEventListener('resize', positionDrawSplitOverlay);
  }
  function undoDrawSplitLine() {
    if (!drawSplitState) return;
    drawSplitState.lines.pop();
    renderDrawSplitLines();
  }
  function boundaryCovered(line, a1, a2) {
    const eps = 3;
    if (line.axis === 'h') return line.x1 <= a1 + eps && line.x2 >= a2 - eps;
    return line.y1 <= a1 + eps && line.y2 >= a2 - eps;
  }
  function buildDrawComponents(lines, width, height) {
    const xs = uniqueSorted(lines.filter(l => l.axis === 'v').map(l => l.x1), width);
    const ys = uniqueSorted(lines.filter(l => l.axis === 'h').map(l => l.y1), height);
    if (xs.length < 2 || ys.length < 2) return null;
    const rows = ys.length - 1;
    const cols = xs.length - 1;
    const seen = Array.from({ length: rows }, () => Array(cols).fill(false));
    const hLines = lines.filter(l => l.axis === 'h');
    const vLines = lines.filter(l => l.axis === 'v');
    const hasHBoundary = (ri, ci) => {
      const y = ys[ri];
      if (ri === 0 || ri === rows) return true;
      return hLines.some(line => Math.abs(line.y1 - y) <= 3 && boundaryCovered(line, xs[ci], xs[ci + 1]));
    };
    const hasVBoundary = (ri, ci) => {
      const x = xs[ci];
      if (ci === 0 || ci === cols) return true;
      return vLines.some(line => Math.abs(line.x1 - x) <= 3 && boundaryCovered(line, ys[ri], ys[ri + 1]));
    };
    const components = [];
    for (let sr = 0; sr < rows; sr++) {
      for (let sc = 0; sc < cols; sc++) {
        if (seen[sr][sc]) continue;
        const queue = [[sr, sc]];
        const cells = [];
        seen[sr][sc] = true;
        while (queue.length) {
          const [r, c] = queue.shift();
          cells.push([r, c]);
          [
            [r - 1, c, !hasHBoundary(r, c)],
            [r + 1, c, !hasHBoundary(r + 1, c)],
            [r, c - 1, !hasVBoundary(r, c)],
            [r, c + 1, !hasVBoundary(r, c + 1)],
          ].forEach(([nr, nc, open]) => {
            if (!open || nr < 0 || nr >= rows || nc < 0 || nc >= cols || seen[nr][nc]) return;
            seen[nr][nc] = true;
            queue.push([nr, nc]);
          });
        }
        const rr = cells.map(item => item[0]);
        const cc = cells.map(item => item[1]);
        const r1 = Math.min(...rr), r2 = Math.max(...rr);
        const c1 = Math.min(...cc), c2 = Math.max(...cc);
        if ((r2 - r1 + 1) * (c2 - c1 + 1) !== cells.length) return null;
        components.push({ r: r1, c: c1, rowspan: r2 - r1 + 1, colspan: c2 - c1 + 1 });
      }
    }
    return { rows, cols, components };
  }
  function uniqueCellsWithPos(table) {
    const { grid } = buildGrid(table);
    const seen = new Set();
    const cells = [];
    for (let r = 0; r < grid.length; r++) {
      const row = grid[r] || [];
      for (let c = 0; c < row.length; c++) {
        const cell = row[c];
        if (!cell || seen.has(cell)) continue;
        seen.add(cell);
        cells.push({ cell, r, c, rowspan: cell.rowSpan || 1, colspan: cell.colSpan || 1 });
      }
    }
    return { grid, cells };
  }
  function setSpanAttrs(cell, rowspan, colspan) {
    if (rowspan > 1) cell.setAttribute('rowspan', String(rowspan));
    else cell.removeAttribute('rowspan');
    if (colspan > 1) cell.setAttribute('colspan', String(colspan));
    else cell.removeAttribute('colspan');
  }
  function distributeUnits(parts, total) {
    const units = Array.from({ length: parts }, () => Math.floor(total / parts));
    let rest = total - units.reduce((sum, value) => sum + value, 0);
    for (let i = 0; i < units.length && rest > 0; i++, rest--) units[i] += 1;
    return units.map(value => Math.max(1, value));
  }
  function prefixSum(values, count) {
    let total = 0;
    for (let i = 0; i < count; i++) total += values[i] || 0;
    return total;
  }
  function spanSum(values, start, count) {
    let total = 0;
    for (let i = start; i < start + count; i++) total += values[i] || 0;
    return Math.max(1, total);
  }
  function expandPatternToTargetSpan(pattern, targetRows, targetCols) {
    const rowUnits = distributeUnits(pattern.rows, targetRows);
    const colUnits = distributeUnits(pattern.cols, targetCols);
    return {
      rows: targetRows,
      cols: targetCols,
      components: pattern.components.map(part => ({
        r: prefixSum(rowUnits, part.r),
        c: prefixSum(colUnits, part.c),
        rowspan: spanSum(rowUnits, part.r, part.rowspan),
        colspan: spanSum(colUnits, part.c, part.colspan),
      })),
    };
  }
  function cloneCellForPlacement(source, rowspan, colspan, html) {
    const cell = document.createElement(source.tagName.toLowerCase());
    for (const attr of Array.from(source.attributes)) {
      if (['rowspan', 'colspan', 'contenteditable'].includes(attr.name)) continue;
      if (attr.name === 'class') {
        const classes = attr.value
          .split(/\s+/)
          .filter(cls => cls && !['__sel', '__editing', '__short', '__drawTarget'].includes(cls));
        if (classes.length) cell.setAttribute('class', classes.join(' '));
        continue;
      }
      cell.setAttribute(attr.name, attr.value);
    }
    cell.innerHTML = html || '';
    setSpanAttrs(cell, rowspan, colspan);
    return cell;
  }
  function rebuildTableWithDrawSplit(target, pattern) {
    const table = target.closest('table');
    if (!table) return false;
    const pos = findCellPos(table, target);
    if (!pos) return false;
    const targetRowspan = target.rowSpan || 1;
    const targetColspan = target.colSpan || 1;
    const expandedPattern = expandPatternToTargetSpan(
      pattern,
      Math.max(pattern.rows, targetRowspan),
      Math.max(pattern.cols, targetColspan)
    );
    const deltaRows = expandedPattern.rows - targetRowspan;
    const deltaCols = expandedPattern.cols - targetColspan;

    const { cells } = uniqueCellsWithPos(table);
    const placements = [];
    cells.forEach(info => {
      if (info.cell === target) return;
      const rowOverlaps = info.r < pos.r + targetRowspan && info.r + info.rowspan > pos.r;
      const colOverlaps = info.c < pos.c + targetColspan && info.c + info.colspan > pos.c;
      const nr = info.r >= pos.r + targetRowspan ? info.r + deltaRows : info.r;
      const nc = info.c >= pos.c + targetColspan ? info.c + deltaCols : info.c;
      const nrs = rowOverlaps ? info.rowspan + deltaRows : info.rowspan;
      const ncs = colOverlaps ? info.colspan + deltaCols : info.colspan;
      placements.push({
        r: nr,
        c: nc,
        cell: cloneCellForPlacement(info.cell, nrs, ncs, info.cell.innerHTML),
      });
    });

    const targetHtml = target.innerHTML;
    expandedPattern.components.forEach((part, idx) => {
      placements.push({
        r: pos.r + part.r,
        c: pos.c + part.c,
        cell: cloneCellForPlacement(target, part.rowspan, part.colspan, idx === 0 ? targetHtml : ''),
      });
    });
    placements.sort((a, b) => (a.r - b.r) || (a.c - b.c));
    const rowCount = Math.max(...placements.map(p => p.r + (p.cell.rowSpan || 1)), 1);
    const rows = Array.from({ length: rowCount }, () => document.createElement('tr'));
    placements.forEach(p => rows[p.r].appendChild(p.cell));

    const captions = Array.from(table.children).filter(ch => ch.tagName === 'CAPTION');
    table.innerHTML = '';
    captions.forEach(caption => table.appendChild(caption));
    const tbody = document.createElement('tbody');
    rows.forEach(row => tbody.appendChild(row));
    table.appendChild(tbody);
    clearSelection();
    const newTarget = rows[pos.r] ? rows[pos.r].querySelector('td,th') : null;
    if (newTarget) selectOne(newTarget);
    return true;
  }
  function applyDrawSplit() {
    if (!drawSplitState || !drawSplitState.target) return;
    if (!drawSplitState.lines.length) {
      alert('분할선을 먼저 그리세요.');
      return;
    }
    const beforeHtml = snapshotHtml();
    const pattern = buildDrawComponents(
      drawSplitState.lines,
      drawSplitState.rect.width,
      drawSplitState.rect.height
    );
    if (!pattern || pattern.components.length <= 1) {
      alert('분할선을 표 구조로 변환할 수 없습니다. 선이 셀 경계 또는 다른 선에 닿도록 그려주세요.');
      return;
    }
    const target = drawSplitState.target;
    removeDrawSplitOverlay();
    if (rebuildTableWithDrawSplit(target, pattern)) {
      rememberSnapshot(beforeHtml);
      schedulePopupUpdate();
    }
  }
  function handleDrawSplitKey(e) {
    if (!drawSplitState) return false;
    if (e.key === 'Escape') {
      removeDrawSplitOverlay();
      e.preventDefault();
      return true;
    }
    return false;
  }

  // ===== 마우스/키보드 =====
  document.addEventListener('mousedown', function (e) {
    if (drawSplitState) return;
    const c = e.target.closest('td, th');
    if (!c) {
      exitTextEditMode();
      return;
    }
    if (e.shiftKey && anchor) {
      exitTextEditMode();
      selectRange(anchor, c);
      clearNativeSelection();
      e.preventDefault();
    } else if (e.ctrlKey || e.metaKey) {
      exitTextEditMode();
      toggleOne(c);
      anchor = c;
      clearNativeSelection();
      e.preventDefault();
    } else if (textEditCell === c || isSingleSelectedCell(c)) {
      enterTextEditMode(c);
      dragStart = null;
      cellDragMode = false;
    } else {
      // 첫 클릭은 셀 선택만 수행하고, 같은 셀 재클릭부터 텍스트 편집을 허용한다.
      exitTextEditMode();
      clearNativeSelection();
      selectOne(c);
      dragStart = c;
      cellDragMode = false;
      e.preventDefault();
    }
  }, true);

  document.addEventListener('mouseover', function (e) {
    if (drawSplitState) return;
    if (!dragStart) return;
    if (e.buttons === 0) { dragStart = null; cellDragMode = false; return; }
    const c = e.target.closest('td, th');
    if (!c) return;
    if (c === dragStart && !cellDragMode) return; // 같은 셀 안에서는 텍스트 선택 허용
    if (!cellDragMode) {
      cellDragMode = true;
      clearNativeSelection();
      selected.add(dragStart); dragStart.classList.add('__sel');
    }
    selectRange(dragStart, c);
    e.preventDefault();
  }, true);

  document.addEventListener('mousemove', function (e) {
    if (drawSplitState) return;
    if (cellDragMode) {
      window.getSelection().removeAllRanges();
      e.preventDefault();
    }
  }, true);

  document.addEventListener('mouseup', function () {
    if (drawSplitState) return;
    if (!cellDragMode && dragStart) {
      selected.add(dragStart); dragStart.classList.add('__sel');
      schedulePopupUpdate();
    }
    dragStart = null;
    cellDragMode = false;
  }, true);

  document.addEventListener('keydown', function (e) {
    if (handleDrawSplitKey(e)) return;
    if (textEditCell) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) {
          insertLineBreakAtCaret();
          return;
        }
        selectCellAfterTextEdit(cellBelow(textEditCell));
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        selectCellAfterTextEdit(nextCell(textEditCell));
      }
      return;
    }
    const selectedCell = selectedEditableCell();
    if (selectedCell && e.key.startsWith('Arrow') && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const target = cellByArrowKey(selectedCell, e.key);
      clearNativeSelection();
      if (target) selectOne(target);
      e.preventDefault();
      return;
    }
    if (selectedCell && e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      beginKeyboardTextEdit(selectedCell);
      e.preventDefault();
      return;
    }
    if (selectedCell && isDirectTextKey(e)) {
      beginKeyboardTextEdit(selectedCell, e.key);
      e.preventDefault();
      return;
    }
    if (
      selectedCell &&
      (e.isComposing || e.key === 'Process' || e.key === 'Unidentified') &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.altKey
    ) {
      beginKeyboardTextEdit(selectedCell);
      return;
    }
    if (!(e.ctrlKey || e.metaKey)) return;
    const k = e.key.toLowerCase();
    if (k === 'z' && !e.shiftKey) {
      if (window.__tableUndo && window.__tableUndo()) e.preventDefault();
      return;
    }
    if (k === 'c') { window.__tableOp('copy'); e.preventDefault(); }
    else if (k === 'x') { window.__tableOp('cut'); e.preventDefault(); }
    else if (k === 'v') { window.__tableOp('paste'); e.preventDefault(); }
  }, true);

  document.addEventListener('input', function (e) {
    const c = e.target && e.target.closest ? e.target.closest('td, th') : null;
    if (c && c === textEditCell) markDirty();
  }, true);

  window.addEventListener('scroll', schedulePopupUpdate, true);
  window.addEventListener('resize', schedulePopupUpdate);

  // ===== 행/열 =====
  function insertRow(offset) {
    const table = activeTable(); if (!table || !last) return;
    const pos = findCellPos(table, last); if (!pos) return;
    const cols = colCount(table);
    const targetIdx = offset > 0 ? (pos.r + (last.rowSpan || 1)) : pos.r;
    const tr = table.insertRow(targetIdx);
    for (let i = 0; i < cols; i++) tr.appendChild(newCell('td'));
  }
  function deleteRow() {
    const table = activeTable(); if (!table) return;
    const trs = new Set();
    selectedInDOMOrder().forEach(c => trs.add(c.parentElement));
    if (trs.size === 0 && last) trs.add(last.parentElement);
    if (table.rows.length - trs.size < 1) return;
    trs.forEach(tr => tr.parentElement.removeChild(tr));
    clearSelection(); last = null;
  }
  function insertCol(offset) {
    const table = activeTable(); if (!table || !last) return;
    const pos = findCellPos(table, last); if (!pos) return;
    const targetCol = offset > 0 ? (pos.c + (last.colSpan || 1)) : pos.c;
    const { rows, grid } = buildGrid(table);
    for (let r = 0; r < rows.length; r++) {
      const left = grid[r] ? grid[r][targetCol - 1] : null;
      const here = grid[r] ? grid[r][targetCol] : null;
      if (left && left === here) {
        if (!left.__expanded) { left.colSpan = (left.colSpan || 1) + 1; left.__expanded = true; }
        continue;
      }
      const row = rows[r];
      let inserted = false;
      for (const cell of Array.from(row.cells)) {
        let startCol = -1;
        for (let cc = 0; cc < grid[r].length; cc++) if (grid[r][cc] === cell) { startCol = cc; break; }
        if (startCol >= targetCol) { row.insertBefore(newCell(cell.tagName), cell); inserted = true; break; }
      }
      if (!inserted) row.appendChild(newCell('td'));
    }
    Array.from(table.querySelectorAll('td,th')).forEach(c => delete c.__expanded);
  }
  function deleteCol() {
    const table = activeTable(); if (!table) return;
    const cols = new Set();
    selectedInDOMOrder().forEach(c => {
      const p = findCellPos(table, c);
      if (p) {
        for (let i = 0; i < (c.colSpan || 1); i++) cols.add(p.c + i);
      }
    });
    if (cols.size === 0 && last) {
      const p = findCellPos(table, last);
      if (p) for (let i = 0; i < (last.colSpan || 1); i++) cols.add(p.c + i);
    }
    if (colCount(table) - cols.size < 1) return;
    const sortedCols = [...cols].sort((a, b) => b - a);
    sortedCols.forEach(targetCol => {
      const { rows, grid } = buildGrid(table);
      const handled = new Set();
      for (let r = 0; r < rows.length; r++) {
        const cell = grid[r] && grid[r][targetCol];
        if (!cell || handled.has(cell)) continue;
        handled.add(cell);
        if ((cell.colSpan || 1) > 1) {
          cell.colSpan = cell.colSpan - 1;
          normalizeCellSpanAttrs(cell);
        }
        else cell.parentElement.removeChild(cell);
      }
    });
    clearSelection(); last = null;
  }

  // ===== 병합/분할 (선택 기준) =====
  function mergeSelection() {
    const rect = selectionRect();
    if (!rect || (rect.r1 === rect.r2 && rect.c1 === rect.c2)) return;
    const { table, r1, c1, r2, c2, grid } = rect;
    for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) {
      const cell = grid[r] && grid[r][c];
      if (!cell || !selected.has(cell)) { alert('선택 영역이 사각형이 아닙니다.'); return; }
    }
    const seen = new Set();
    for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) {
      const cell = grid[r][c];
      if (seen.has(cell)) continue;
      seen.add(cell);
      const p = findCellPos(table, cell);
      const re = p.r + (cell.rowSpan || 1) - 1;
      const ce = p.c + (cell.colSpan || 1) - 1;
      if (p.r < r1 || p.c < c1 || re > r2 || ce > c2) {
        alert('영역 밖으로 튀어나간 병합 셀이 있습니다.'); return;
      }
    }
    const head = grid[r1][c1];
    const parts = [];
    seen.forEach(cell => {
      clearBlankCellPlaceholder(cell);
      const t = cell.innerHTML.trim();
      if (t) parts.push(t);
    });
    head.innerHTML = parts.join(' ');
    head.colSpan = c2 - c1 + 1;
    head.rowSpan = r2 - r1 + 1;
    seen.forEach(cell => { if (cell !== head) cell.parentElement.removeChild(cell); });
    clearSelection(); selectOne(head);
  }
  function splitCells() {
    const targets = selectedInDOMOrder().filter(c => (c.colSpan || 1) > 1 || (c.rowSpan || 1) > 1);
    if (targets.length === 0 && last && ((last.colSpan || 1) > 1 || (last.rowSpan || 1) > 1)) targets.push(last);
    targets.forEach(splitOne);
    clearSelection();
  }
  function splitOne(cell) {
    const table = cell.closest('table');
    const pos = findCellPos(table, cell); if (!pos) return;
    const cs = cell.colSpan || 1, rs = cell.rowSpan || 1;
    if (cs <= 1 && rs <= 1) return;
    cell.removeAttribute('colspan');
    cell.removeAttribute('rowspan');
    const rows = table.rows;
    for (let dr = 0; dr < rs; dr++) {
      for (let dc = 0; dc < cs; dc++) {
        if (dr === 0 && dc === 0) continue;
        const tr = rows[pos.r + dr]; if (!tr) continue;
        const { grid } = buildGrid(table);
        let inserted = false;
        for (const c of Array.from(tr.cells)) {
          let startCol = -1;
          for (let cc = 0; cc < (grid[pos.r + dr] || []).length; cc++) if (grid[pos.r + dr][cc] === c) { startCol = cc; break; }
          if (startCol >= pos.c + dc) { tr.insertBefore(newCell('td'), c); inserted = true; break; }
        }
        if (!inserted) tr.appendChild(newCell('td'));
      }
    }
  }

  // ===== 헤더 지정/해제 =====
  function swapTag(cell, tag) {
    if (cell.tagName.toLowerCase() === tag) return cell;
    const ne = document.createElement(tag);
    for (const a of Array.from(cell.attributes)) {
      if (a.name === 'class' && !a.value.trim()) continue;
      ne.setAttribute(a.name, a.value);
    }
    ne.innerHTML = cell.innerHTML;
    cell.parentElement.replaceChild(ne, cell);
    return ne;
  }
  // ===== tfoot 이동 =====
  // 선택된 셀이 속한 행 단위로 tfoot ↔ tbody 사이를 이동.
  // 선택이 없으면 last 셀이 속한 행만 처리.
  function rowsFromSelection() {
    let targets = selectedInDOMOrder();
    if (targets.length === 0 && last) targets = [last];
    const rows = new Set();
    targets.forEach(c => { const tr = c.closest('tr'); if (tr) rows.add(tr); });
    return Array.from(rows);
  }
  function ensureTbody(table) {
    let tbody = table.querySelector(':scope > tbody');
    if (tbody) return tbody;
    tbody = document.createElement('tbody');
    // 직접 자식인 tr들을 tbody로 묶고, tfoot 앞에 삽입
    const stray = Array.from(table.children).filter(ch => ch.tagName === 'TR');
    stray.forEach(tr => tbody.appendChild(tr));
    const tfoot = table.querySelector(':scope > tfoot');
    if (tfoot) table.insertBefore(tbody, tfoot);
    else table.appendChild(tbody);
    return tbody;
  }
  function setFooterImpl() {
    const table = activeTable(); if (!table) return;
    const rows = rowsFromSelection(); if (rows.length === 0) return;
    let tfoot = table.querySelector(':scope > tfoot');
    if (!tfoot) {
      tfoot = document.createElement('tfoot');
      table.appendChild(tfoot);
    }
    rows.forEach(tr => { if (tr.parentNode !== tfoot) tfoot.appendChild(tr); });
  }
  function unsetFooterImpl() {
    const table = activeTable(); if (!table) return;
    const rows = rowsFromSelection(); if (rows.length === 0) return;
    const tbody = ensureTbody(table);
    rows.forEach(tr => {
      if (tr.parentNode && tr.parentNode.tagName === 'TFOOT') tbody.appendChild(tr);
    });
    const tfoot = table.querySelector(':scope > tfoot');
    if (tfoot && tfoot.children.length === 0) tfoot.remove();
  }

  function convertSelection(tag) {
    let targets = selectedInDOMOrder();
    if (targets.length === 0 && last) targets = [last];
    if (targets.length === 0) return;
    const wasSelected = new Set(selected);
    const wasLast = last;
    clearSelection();
    targets.forEach(c => {
      const isSel = wasSelected.has(c);
      const isLast = c === wasLast;
      const ne = swapTag(c, tag);
      if (isSel) { selected.add(ne); ne.classList.add('__sel'); }
      if (isLast) { last = ne; anchor = ne; }
    });
  }

  // ===== 클립보드 =====
  function copyImpl(clear) {
    const cells = selectedInDOMOrder();
    if (cells.length === 0) return;
    const rect = selectionRect();
    let rows = null, cols = null;
    if (rect) {
      rows = rect.r2 - rect.r1 + 1;
      cols = rect.c2 - rect.c1 + 1;
    }
    clipboard = {
      cells: cells.map(c => c.innerHTML),
      count: cells.length,
      rows, cols
    };
    if (clear) {
      cells.forEach(c => c.innerHTML = '');
    }
  }
  function pasteImpl() {
    if (!clipboard) { alert('클립보드가 비어 있습니다.'); return; }
    const targets = selectedInDOMOrder();
    if (targets.length === 0) { alert('붙여넣을 셀을 선택하세요.'); return; }
    if (targets.length !== clipboard.count) {
      alert('선택한 셀 개수(' + targets.length + ')와 클립보드(' + clipboard.count + ')가 다릅니다.');
      return;
    }
    targets.forEach((c, i) => { c.innerHTML = clipboard.cells[i]; });
  }

  // ===== 열 개수 정합성 =====
  function addCellAtRowEnd() {
    if (!last) return;
    const row = last.parentElement;
    row.appendChild(newCell(last.tagName.toLowerCase()));
  }
  function normalizeRows() {
    const table = activeTable(); if (!table) return;
    const { rows, grid } = buildGrid(table);
    const maxCols = Math.max(...grid.map(r => r ? r.length : 0));
    rows.forEach((row, ri) => {
      const cur = grid[ri] ? grid[ri].length : 0;
      for (let i = cur; i < maxCols; i++) row.appendChild(newCell('td'));
    });
  }
  window.__getRowColInfo = function () {
    const ed = document.getElementById('editable');
    if (!ed) return null;
    const tables = ed.querySelectorAll('table');
    if (!tables.length) return null;
    const out = [];
    tables.forEach((t, ti) => {
      const { grid } = buildGrid(t);
      grid.forEach((row, ri) => {
        out.push({ t: ti, r: ri, c: row ? row.length : 0 });
      });
      const maxCols = Math.max(...grid.map(r => r ? r.length : 0));
      Array.from(t.rows).forEach(tr => tr.classList.remove('__short'));
      grid.forEach((row, ri) => {
        if (row && row.length < maxCols && t.rows[ri]) t.rows[ri].classList.add('__short');
      });
    });
    return out;
  };

  // ===== ops 디스패치 =====
  const ops = {
    addRowAbove: () => insertRow(-1),
    addRowBelow: () => insertRow(+1),
    addColLeft:  () => insertCol(-1),
    addColRight: () => insertCol(+1),
    delRow:      deleteRow,
    delCol:      deleteCol,
    mergeSelection,
    splitCell:   splitCells,
    drawSplitMode: enterDrawSplitMode,
    setHeader:   () => convertSelection('th'),
    unsetHeader: () => convertSelection('td'),
    setFooter:   setFooterImpl,
    unsetFooter: unsetFooterImpl,
    cut:    () => copyImpl(true),
    copy:   () => copyImpl(false),
    paste:  pasteImpl,
    addCellEnd:     addCellAtRowEnd,
    normalizeTable: normalizeRows,
  };
  function applyTableOp(name) {
    const beforeHtml = snapshotHtml();
    exitTextEditMode();
    clearNativeSelection();
    if (ops[name]) ops[name]();
    rememberSnapshot(beforeHtml);
    schedulePopupUpdate();
    return true;
  }
  window.__getEditableHtml = currentEditableHtml;
  window.__peekEditableHtml = peekEditableHtml;
  window.__consumeTableDirtyHtml = consumeDirtyHtml;
  window.__tableOp = applyTableOp;
  window.__tableUndo = undoLastAction;

  // ===== 스타일 =====
  const style = document.createElement('style');
  style.textContent =
    '.__sel{outline:2px solid #F97316 !important; outline-offset:-2px;' +
    ' background-color: rgba(249,115,22,0.15) !important;}' +
    '.__editing{outline:2px solid #2563EB !important; outline-offset:-2px;' +
    ' background-color: rgba(37,99,235,0.10) !important;}' +
    '.__drawTarget{outline:3px solid #7C3AED !important; outline-offset:-3px;' +
    ' background-color: rgba(124,58,237,0.08) !important;}' +
    'td,th{cursor:default;}' +
    'td[contenteditable="true"],th[contenteditable="true"]{cursor:text;}' +
    '#__drawSplitOverlay{position:fixed; z-index:99998; box-sizing:border-box;' +
    ' border:2px dashed #7C3AED; background:rgba(124,58,237,0.04); cursor:crosshair;}' +
    '#__drawSplitOverlay .__drawSvg{position:absolute; inset:0; width:100%; height:100%; overflow:visible;}' +
    '#__drawSplitOverlay .__drawLine{stroke:#111827; stroke-width:3; stroke-linecap:round; pointer-events:none;}' +
    '#__drawSplitOverlay .__drawLine.__draft{stroke:#7C3AED; stroke-dasharray:7 5;}' +
    '#__drawSplitOverlay .__drawToolbar{position:absolute; left:0; top:-42px; display:flex; align-items:center; gap:6px;' +
    ' padding:6px 8px; background:#ffffff; border:1px solid #d8dee8; border-radius:10px;' +
    ' box-shadow:0 10px 22px rgba(15,23,42,0.14); cursor:default; white-space:nowrap;}' +
    '#__drawSplitOverlay .__drawToolbar span{font-size:11px; color:#64748b; font-weight:700;}' +
    '#__drawSplitOverlay .__drawToolbar button{background:#ffffff; color:#334155; border:1px solid #d8dee8;' +
    ' border-radius:8px; padding:4px 9px; font-size:12px; font-weight:700; cursor:pointer;}' +
    '#__drawSplitOverlay .__drawToolbar button:hover{background:#eff6ff; border-color:#93c5fd; color:#1d4ed8;}' +
    '#__selectionPopup{position:fixed; z-index:99999; display:flex; flex-wrap:wrap;' +
    ' gap:8px; width:fit-content; min-width:min(540px, calc(100vw - 16px)); max-width:calc(100vw - 16px);' +
    ' padding:10px; background:#ffffff; border:1px solid #d8dee8;' +
    ' border-radius:12px; box-shadow:0 14px 32px rgba(15,23,42,0.16);}' +
    '#__selectionPopup[hidden]{display:none !important;}' +
    '#__selectionPopup [hidden]{display:none !important;}' +
    '#__selectionPopup .__popupHeader{flex:1 0 100%; display:flex; align-items:center;' +
    ' min-height:24px; padding:0 2px 2px; color:#64748b; font-size:11px; font-weight:700; cursor:move; user-select:none;}' +
    '#__selectionPopup .__popupSection{display:flex; flex:0 0 auto; min-width:132px; flex-direction:column;' +
    ' gap:6px; padding:8px; background:#f8fafc; border:1px solid #edf1f7; border-radius:10px;}' +
    '#__selectionPopup .__popupSectionTitle{color:#64748b; font-size:11px; font-weight:700;}' +
    '#__selectionPopup .__popupActions{display:flex; flex-direction:column; gap:6px;}' +
    '#__selectionPopup button{background:#ffffff; color:#334155; border:1px solid #d8dee8;' +
    ' border-radius:8px; padding:5px 10px; min-width:112px; min-height:30px; font-size:12px; font-weight:600; cursor:pointer;' +
    ' white-space:normal; word-break:keep-all; line-height:1.2; text-align:center;}' +
    '#__selectionPopup button:hover:not(:disabled){background:#eff6ff; border-color:#93c5fd; color:#1d4ed8;}' +
    '#__selectionPopup button:disabled{background:#f8fafc; color:#94a3b8; border-color:#e2e8f0; cursor:default;}' +
    'tr.__short > *:first-child{box-shadow: -3px 0 0 #EF4444 inset;}';
  document.head.appendChild(style);
  resetCurrentSnapshot();
})();
