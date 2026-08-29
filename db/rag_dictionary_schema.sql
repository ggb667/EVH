CREATE TABLE IF NOT EXISTS rag_dictionary_term (
    id BIGINT NOT NULL AUTO_INCREMENT,
    term_type VARCHAR(64) NOT NULL,
    canonical_name VARCHAR(255) NOT NULL,
    aliases JSON NOT NULL,
    category VARCHAR(191) DEFAULT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    priority_score INT NOT NULL DEFAULT 100,
    confidence_score DECIMAL(6,4) NOT NULL DEFAULT 1.0000,
    metadata_json JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY rag_dictionary_term_type_name_uniq (term_type, canonical_name),
    KEY rag_dictionary_term_type_idx (term_type),
    KEY rag_dictionary_term_category_idx (category),
    KEY rag_dictionary_term_active_idx (active),
    KEY rag_dictionary_term_priority_idx (priority_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS rag_dictionary_term_alias (
    id BIGINT NOT NULL AUTO_INCREMENT,
    dictionary_term_id BIGINT NOT NULL,
    alias_text VARCHAR(255) NOT NULL,
    alias_kind VARCHAR(64) DEFAULT NULL,
    confidence_score DECIMAL(6,4) NOT NULL DEFAULT 1.0000,
    source_note VARCHAR(255) DEFAULT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY rag_dictionary_term_alias_uniq (dictionary_term_id, alias_text),
    KEY rag_dictionary_term_alias_text_idx (alias_text),
    CONSTRAINT rag_dictionary_term_alias_fk
        FOREIGN KEY (dictionary_term_id) REFERENCES rag_dictionary_term (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
