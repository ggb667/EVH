CREATE TABLE IF NOT EXISTS instinct_accounts (
    id CHAR(36) NOT NULL,
    pims_code VARCHAR(191) NOT NULL,
    pims_id VARCHAR(191) DEFAULT NULL,
    owner_first_name VARCHAR(191) NOT NULL DEFAULT '',
    owner_last_name VARCHAR(191) NOT NULL DEFAULT '',
    display_name VARCHAR(255) NOT NULL DEFAULT '',
    primary_phone VARCHAR(64) NOT NULL DEFAULT '',
    email_addresses JSON NOT NULL,
    communication_details JSON NOT NULL,
    updated_at DATETIME(6) DEFAULT NULL,
    deleted_at DATETIME(6) DEFAULT NULL,
    is_deleted TINYINT(1) NOT NULL DEFAULT 0,
    raw_payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    modified_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY instinct_accounts_pims_code_uniq (pims_code),
    KEY instinct_accounts_display_name_idx (display_name),
    KEY instinct_accounts_owner_name_idx (owner_last_name, owner_first_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS instinct_patients (
    id BIGINT NOT NULL,
    account_id CHAR(36) NOT NULL,
    pims_code VARCHAR(191) DEFAULT NULL,
    name VARCHAR(255) NOT NULL DEFAULT '',
    birthdate DATE DEFAULT NULL,
    sex_id VARCHAR(64) DEFAULT NULL,
    species_id VARCHAR(64) DEFAULT NULL,
    breed VARCHAR(255) DEFAULT NULL,
    deceased_date DATE DEFAULT NULL,
    deleted_at DATETIME(6) DEFAULT NULL,
    merged_into_patient_id BIGINT DEFAULT NULL,
    alerts JSON NOT NULL,
    raw_payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    modified_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY instinct_patients_account_pims_code_uniq (account_id, pims_code),
    KEY instinct_patients_account_id_idx (account_id),
    KEY instinct_patients_name_idx (name),
    KEY instinct_patients_pims_code_idx (pims_code),
    CONSTRAINT instinct_patients_account_fk
        FOREIGN KEY (account_id) REFERENCES instinct_accounts (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
