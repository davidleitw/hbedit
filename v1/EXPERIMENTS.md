# hbedit POC — 實驗記錄

> 本檔由 `poc.py` 自動產生,內容直接反映實際執行結果。

- 執行時間:2026-05-22 01:06:29
- Heptabase CLI:0.3.0

## 總覽

| 實驗 | 主題 | 狀態 |
|---|---|---|
| E01 | 進階 schema 探索 | ✅ PASS |
| E02 | Pull 保真度(進階 schema) | ✅ PASS |
| E03 | 卡片引用能否由 markdown 建立 | ⚠️ WARN |
| E04 | append 語意 | ✅ PASS |
| E05 | save:JSON 層級的 block 增 / 刪 / 重排 | ✅ PASS |
| E06 | Push:編輯過的 markdown 經 transplant 推回 | ✅ PASS |
| E07 | Push:純重排 block 順序 | ✅ PASS |
| E08 | 衝突偵測與樂觀鎖復原 | ✅ PASS |
| E09 | Tag 與 property 讀寫 | ✅ PASS |
| E10 | 遠端變更偵測(輪詢) | ✅ PASS |
| E11 | Whiteboard 成員關係 | ✅ PASS |
| E12 | 邊界情況:CJK / emoji / 空內容 / 多 block | ✅ PASS |
| E13 | Push:純標記變更(加粗體) | ✅ PASS |
| E14 | Push:標題層級變更與巢狀清單編輯 | ✅ PASS |
| E15 | Push:含表格 / 數學的卡片局部編輯 | ✅ PASS |
| E16 | Journal 讀取(date-keyed 卡片) | ✅ PASS |
| E17 | Card trash / restore 往返 | ✅ PASS |
| E18 | 端到端同步循環(pull → 本地 .md → 編輯 → push) | ✅ PASS |
| E19 | Frontmatter schema 往返 | ✅ PASS |
| E20 | 寫入吞吐量(daemon 同步速率估算) | ✅ PASS |
| E21 | 內容大小上限 | ✅ PASS |

---

## E01 — 進階 schema 探索

**測試什麼**

探索 Heptabase 對 todo、分隔線、表格、行內/區塊數學、圖片、混合巢狀清單等進階 markdown 會產生哪些 ProseMirror node/mark 類型 —— 這是轉換器必須支援的完整詞彙表。

**怎麼測試**

1. 用一份涵蓋上述 7 類進階語法的 markdown 建立一張 note。
2. `note read` 讀回,統計所有 node type 與 mark type。
3. 把完整 JSON 存到 fixtures/schema_extended.json 供檢視。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| node/mark 詞彙表 | ℹ️ INFO | bullet_list_item, doc, heading, horizontal_rule, image, math_display, math_inline, numbered_list_item, paragraph, table, table_cell, table_header, table_row, text, todo_list_item |
| todo / checkbox 有對應 node | ✅ PASS | node type: todo_list_item |
| 分隔線 horizontal rule 有對應 node | ✅ PASS | node type: horizontal_rule |
| 表格 table 有對應 node | ✅ PASS | node type: table |
| 數學 math 有對應 node | ✅ PASS | node type: math_inline |
| 圖片 image 有對應 node | ✅ PASS | node type: image |

---

## E02 — Pull 保真度(進階 schema)

**測試什麼**

驗證 pm2md 轉換器能否無損地把 E01 的進階 schema 轉回 markdown,並誠實回報任何無法處理的 node/mark。

**怎麼測試**

1. 取 E01 卡片的 ProseMirror JSON。
2. 用 pm2md 轉成 markdown。
3. 輸出存到 fixtures/roundtrip_extended.md。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 所有 node 類型都能處理 | ✅ PASS | — |
| 所有 mark 類型都能處理 | ✅ PASS | — |
| 輸出無資料遺失標記 | ✅ PASS | — |

---

## E03 — 卡片引用能否由 markdown 建立

**測試什麼**

Heptabase 的卡片對卡片引用是 inline `card` node。測試能否透過 `note create` 的 markdown 建立這種引用 —— 若不行,daemon 將無法從本地 markdown 同步引用關係。

**怎麼測試**

1. 建立目標卡 A (E03 Target Card),id=e7595cc5-7107-4c84-921d-bb13fad03eb8。
2. 嘗試語法「wiki-link 標題」:`[[E03 Target Card]]`。
3. 嘗試語法「wiki-link cardId」:`[[e7595cc5-7107-4c84-921d-bb13fad03eb8]]`。
4. 嘗試語法「markdown link 指向 cardId」:`[E03 Target Card](e7595cc5-7107-4c84-921d-bb13fad03eb8)`。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| wiki-link 標題 未產生引用 | ⚠️ WARN | 被當成純文字 / 一般連結 |
| wiki-link cardId 未產生引用 | ⚠️ WARN | 被當成純文字 / 一般連結 |
| markdown link 指向 cardId 未產生引用 | ⚠️ WARN | 被當成純文字 / 一般連結 |
| 結論:markdown 無法建立卡片引用 | ⚠️ WARN | 引用關係需在 app 內建立;daemon 對引用只能唯讀 |

---

## E04 — append 語意

**測試什麼**

確認 `note append` 如何與既有內容互動:是否保留既有 block 的 ID、多次 append 是否都生效。

**怎麼測試**

1. 建卡,記錄既有 2 個 block ID。
2. append 第一段 markdown。
3. append 第二段 markdown。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 既有 block ID 全數保留 | ✅ PASS | 2/2 保留 |
| 第一次 append 內容存在 | ✅ PASS | — |
| 第二次 append 內容存在 | ✅ PASS | — |
| append 確實新增了 block | ✅ PASS | 2 -> 6 個 block |

---

## E05 — save:JSON 層級的 block 增 / 刪 / 重排

**測試什麼**

確認 `note save` 能可靠處理 ProseMirror JSON 層級的 block 新增、刪除、重排,且未動到的 block 其 ID 維持不變。

**怎麼測試**

1. 讀 JSON,在尾端插入一個自帶新 UUID 的 paragraph 後 save。
2. 移除 'Beta.' 那個 block 後 save。
3. 交換第 2、3 個 block 的順序後 save。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 新增的 block 出現 | ✅ PASS | — |
| 新增後既有 ID 不變 | ✅ PASS | — |
| 刪除的 block 消失 | ✅ PASS | — |
| 重排後順序生效 | ✅ PASS | E05 Save / Gamma. / Alpha. / Delta (added via JSON). |

---

## E06 — Push:編輯過的 markdown 經 transplant 推回

**測試什麼**

核心實驗。一份被 agent 編輯過(改一段、刪一段、加一段)的 markdown,能否在保留未變更 block ID 的前提下推回 Heptabase。策略:讓 Heptabase 把編輯後 markdown 轉成 ProseMirror(scratch 卡),再把原卡的 block ID 移植到存活的 block 上。

**怎麼測試**

1. 建立原始卡 C(標題 + 4 段),記錄每段的 block ID。
2. 用 pm2md 把 C 拉成 markdown,模擬 agent 編輯:改第 2 段、刪第 3 段、文末新增第 5 段。
3. 用編輯後 markdown 建 scratch 卡 S(由 Heptabase 做 MD→PM)。
4. transplant_ids() 把舊 ID 移植到存活的 block。
5. `note save` 把移植後的 JSON 寫回 C。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 未變更的 3 個 block 保留原 ID | ✅ PASS | preserved=3 |
| 被編輯的第 2 段保留原 ID(edited) | ✅ PASS | edited=['2375bff4-f217-43e2-a328-0a1a9ec326b2'] |
| 被刪除的第 3 段舊 ID 已消失 | ✅ PASS | — |
| 新增的第 5 段為全新 ID | ✅ PASS | — |
| 最終卡片內容等於編輯後 markdown | ✅ PASS | — |

---

## E07 — Push:純重排 block 順序

**測試什麼**

測試只是調換 block 順序(內容不變)時,transplant 能否讓 ID 跟著 block 走,而不是被當成刪除 + 新增。

**怎麼測試**

1. 建卡(A / B / C 三段),記錄各段 ID。
2. 把順序改為 C / A / B,建 scratch 卡。
3. transplant + save。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| Block A 保留原 ID | ✅ PASS | — |
| Block B 保留原 ID | ✅ PASS | — |
| Block C 保留原 ID | ✅ PASS | — |
| 最終順序為 C / A / B | ✅ PASS | Block C. Block A. Block B. |

---

## E08 — 衝突偵測與樂觀鎖復原

**測試什麼**

驗證 `--content-md5` 樂觀鎖:合法 save 成功、過期 md5 被拒、重新 read 後重試可成功復原 —— 這是 daemon 衝突處理的基礎。

**怎麼測試**

1. 建卡,read 取得 md5_1。
2. 用 md5_1 做一次合法編輯 save(內容變更);md5_1 自此過期。
3. 再用已過期的 md5_1 嘗試 save → 預期被拒。
4. 復原:重新 read 取得 md5_2,帶 md5_2 重試 → 預期成功。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 帶正確 md5 的 save 成功 | ✅ PASS | — |
| 過期 md5 的 save 被拒 | ✅ PASS | Content conflict: the card has been modified since you last read it. Run \ |
| 重新 read 取得新 md5 後重試成功 | ✅ PASS | — |

---

## E09 — Tag 與 property 讀寫

**測試什麼**

測試 tag 與結構化 property 能否經 CLI 讀寫 —— 對應把 tag / property 放進本地 markdown frontmatter 並同步的構想。

**怎麼測試**

1. 沿用既有 tag「aem」(不新增,避免汙染)。
2. 把該 tag 加到一張 throwaway 卡上。
3. 對文字屬性「issue_num」set-property 後重讀驗證。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| CLI 無 tag 刪除指令 | ℹ️ INFO | 故 POC 不主動建立 tag |
| 可讀取 tag 的 property schema | ✅ PASS | 3 個欄位 |
| 可讀取卡片的結構化屬性 | ✅ PASS | 卡片掛了 1 個 tag |
| set-property 寫入文字屬性並可讀回 | ✅ PASS | — |

---

## E10 — 遠端變更偵測(輪詢)

**測試什麼**

CLI 沒有事件推送,daemon 只能輪詢。測試 `card list` 的 lastEditedTime 是否能用來偵測遠端變更。

**怎麼測試**

1. 建卡,`card list` 取得其 lastEditedTime。
2. save 一次編輯。
3. 再次 `card list`,比對 lastEditedTime。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| card list 查得到該卡 | ✅ PASS | — |
| lastEditedTime 在編輯後前進 | ✅ PASS | 2026-05-21T17:06:33.814Z -> 2026-05-21T17:06:34.229Z |
| 剛編輯的卡排在 lastUpdatedTime 前段 | ✅ PASS | 排名第 1 |

---

## E11 — Whiteboard 成員關係

**測試什麼**

測試卡片加入 / 移出 whiteboard 是否可由 CLI 控制 —— 對應 frontmatter 的 `whiteboard:` 欄位。

**怎麼測試**

1. 沿用既有 whiteboard「c++」。
2. `whiteboard add-card` 後用 `whiteboard cards` 確認。
3. `whiteboard remove-card` 後再確認。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| add-card 後卡片出現在 whiteboard 上 | ✅ PASS | — |
| remove-card 後卡片已移除 | ✅ PASS | — |
| CLI 無法控制座標 | ℹ️ INFO | frontmatter 只能表達『屬於哪個白板』,不能定位 |

---

## E12 — 邊界情況:CJK / emoji / 空內容 / 多 block

**測試什麼**

測試非 ASCII 內容、空內容、以及較多 block 的卡片是否正常。

**怎麼測試**

1. 建立含繁中、emoji、markdown 特殊字元的卡並 round-trip。
2. 嘗試用空 markdown 建卡,觀察行為。
3. 建立一張 ~120 個 block 的卡,確認 create + read 正常。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| CJK 與 emoji 正確 round-trip | ✅ PASS | — |
| 空內容被拒(符合預期) | ✅ PASS | String must contain at least 1 character(s) |
| 多 block 卡片正常建立並讀回 | ✅ PASS | 121 個 block |

---

## E13 — Push:純標記變更(加粗體)

**測試什麼**

若 agent 只是把某個字加粗(純文字不變),transplant 的 signature 是 type + 純文字,該 block 會被判為 equal。驗證:即使判為 equal,save 寫入的仍是 scratch 卡內容(含粗體),所以標記變更不會遺失。

**怎麼測試**

1. 建卡,內容含一個普通段落。
2. 把 'important' 加粗,建 scratch 卡。
3. transplant + save 回原卡。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 粗體標記確實寫入(變更未遺失) | ✅ PASS | — |
| 段落 block 保留原 ID | ✅ PASS | transplant 分類:preserved |

---

## E14 — Push:標題層級變更與巢狀清單編輯

**測試什麼**

測試 transplant 對(a)標題層級改變(## → ###)與(b)巢狀清單子項目文字編輯的處理。

**怎麼測試**

1. 建卡:含一個 H2 與一個帶子項目的清單。
2. 把 H2 改成 H3、子項目文字加上 'edited',transplant + save。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 標題層級變更生效(### 出現) | ✅ PASS | — |
| 巢狀子項目文字變更生效 | ✅ PASS | — |
| 標題層級存在 attrs.level | ℹ️ INFO | type 不變,transplant 視為 equal 並存回新 level |

---

## E15 — Push:含表格 / 數學的卡片局部編輯

**測試什麼**

在同時含表格與數學的卡片上只編輯其中一段文字。驗證 transplant 後表格、數學等複雜 node 完整保留,且只有被編輯的段落改變。

**怎麼測試**

1. 建卡:段落 + 表格 + 行內數學段 + 區塊數學。
2. 只把第一段文字改掉,transplant + save。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 表格 node 完整保留 | ✅ PASS | — |
| 區塊數學 node 完整保留 | ✅ PASS | — |
| 行內數學 node 完整保留 | ✅ PASS | — |
| 被編輯的段落內容已更新 | ✅ PASS | — |

---

## E16 — Journal 讀取(date-keyed 卡片)

**測試什麼**

Journal 用日期當 key 而非 UUID。讀取今天的 journal,確認其結構與 note 相同(ProseMirror JSON + contentMd5),可納入同步模型。為避免汙染使用者的真實 journal,本實驗只做唯讀。

**怎麼測試**

1. `journal read 2026-05-22`。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| journal 內容也是 ProseMirror JSON | ✅ PASS | — |
| journal 也回傳 contentMd5(可做樂觀鎖) | ✅ PASS | — |
| journal 的 key 是日期 | ℹ️ INFO | date=2026-05-22,非 UUID |

---

## E17 — Card trash / restore 往返

**測試什麼**

確認 trash 是軟刪除、可被 restore。這讓 daemon 的刪除同步是安全的(本地刪檔導致的遠端 trash 可復原)。

**怎麼測試**

1. 建卡。
2. trash 該卡。
3. restore 該卡。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| trash 後可 restore 並重新讀取 | ✅ PASS | 標題:E17 Trash |

---

## E18 — 端到端同步循環(pull → 本地 .md → 編輯 → push)

**測試什麼**

模擬 v1 daemon 完整一輪:把一張卡 pull 成帶 frontmatter 的本地 .md、編輯 body、再 push 回去。這是把所有零件串起來的總驗證。

**怎麼測試**

1. 建立來源卡 C。
2. pull:pm2md 轉成 markdown body,加上 heptabase frontmatter,組成本地 .md 檔內容。
3. agent 編輯:解析出 body,改第一段文字(frontmatter 不動)。
4. push:用編輯後 body 建 scratch 卡、transplant block ID、save 回 C。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 本地 .md 以 frontmatter 開頭且含 cardId | ✅ PASS | — |
| 解析回的 cardId 與原卡一致 | ✅ PASS | — |
| 編輯後內容成功 push 回原卡 | ✅ PASS | — |
| 未編輯的第二段保留原 block ID | ✅ PASS | — |
| 完整循環不丟資料(第二段仍在) | ✅ PASS | — |

---

## E19 — Frontmatter schema 往返

**測試什麼**

驗證 v1 的 frontmatter 模組:serialize → parse 能無損往返 schema 中所有欄位類型(字串、清單、空清單、含特殊字元的標題)。

**怎麼測試**

1. 構造一份含特殊字元標題、清單、空清單的 meta。
2. serialize 後再 parse。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| frontmatter 往返後 meta 完全一致 | ✅ PASS | — |
| body 往返後完全一致 | ✅ PASS | — |
| 無 frontmatter 的純 markdown 也能安全解析 | ✅ PASS | — |

---

## E20 — 寫入吞吐量(daemon 同步速率估算)

**測試什麼**

寫操作是序列化的。量測連續 N 次 note 寫入的耗時,估算 daemon 同步一個 vault 的速率上限。

**怎麼測試**

1. 連續建立 8 張卡並計時。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 總耗時 / 平均單次 | ℹ️ INFO | 0.76s 共 8 次,平均 95 ms/次 |
| 單次寫入在合理範圍(< 2s) | ✅ PASS | 95 ms/次 |
| vault 同步速率推估 | ℹ️ INFO | 約 634 張卡/分鐘(僅寫入,序列化) |

---

## E21 — 內容大小上限

**測試什麼**

探測單張卡片 markdown 內容的大小上限。skill 文件記載 request body 上限為 1MB,但實測有更嚴格的字元數限制 —— 這對 daemon 處理超長卡片是關鍵約束。

**怎麼測試**

1. 建立一張約 95,000 字元的卡(預期低於上限)。
2. 建立一張約 120,000 字元的卡(預期被拒)。
3. 建一張 900-block 的卡(markdown 僅約 12K,但其 ProseMirror JSON 會超過 100K),讀回 JSON 後嘗試 save。

**結果**

| 檢查項 | 狀態 | 觀察 |
|---|---|---|
| 95K 字元的卡片可正常建立 | ✅ PASS | 2 個 block |
| 超過上限的 create 被拒 | ✅ PASS | String must contain at most 100000 character(s) |
| save 的 100K 上限作用在 ProseMirror JSON payload 上 | ✅ PASS | markdown 僅約 12K,但 JSON 長 121551 字元而被拒 |
| 實測上限與意涵 | ℹ️ INFO | create 驗證 markdown、save 驗證 ProseMirror JSON,各有 100,000 字元上限。JSON 約為 markdown 的數倍,故 push(note save)能推送的卡片遠小於 100K markdown;daemon 需對超長卡片分段或拒絕同步 |

