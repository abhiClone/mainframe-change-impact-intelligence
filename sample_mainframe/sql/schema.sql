-- ==================================================================
-- DB2 schema for the synthetic automotive after-sales application.
-- SYNTHETIC DATA ONLY. No proprietary content.
-- ==================================================================

CREATE TABLE CUSTOMER (
    CUST_ID     CHAR(10)    NOT NULL PRIMARY KEY,
    CUST_NAME   VARCHAR(60) NOT NULL,
    CUST_TIER   CHAR(1)     NOT NULL,
    CUST_REGION CHAR(3),
    CUST_SINCE  DATE
);

CREATE TABLE WARRANTY (
    WARRANTY_ID     CHAR(12)     NOT NULL PRIMARY KEY,
    WARRANTY_STATUS CHAR(2)      NOT NULL,
    CLAIM_AMOUNT    DECIMAL(11,2),
    CLAIM_DATE      DATE,
    VEH_ID          CHAR(12),
    CUST_ID         CHAR(10)
);

CREATE TABLE VEHICLE (
    VEH_ID     CHAR(12)    NOT NULL PRIMARY KEY,
    VEH_VIN    CHAR(17)    NOT NULL,
    VEH_MAKE   VARCHAR(20),
    VEH_MODEL  VARCHAR(20),
    VEH_YEAR   INTEGER,
    VEH_OWNER  CHAR(10)
);

CREATE TABLE CLAIM_HISTORY (
    HIST_SEQ     INTEGER     NOT NULL PRIMARY KEY,
    WARRANTY_ID  CHAR(12)    NOT NULL,
    ACTION_CODE  CHAR(4)     NOT NULL,
    ACTION_TS    TIMESTAMP   NOT NULL
);
