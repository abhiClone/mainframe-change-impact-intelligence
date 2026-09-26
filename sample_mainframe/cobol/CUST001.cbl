       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUST001.
       AUTHOR. SYNTHETIC-DATA.
      ******************************************************************
      * CUST001 - Customer master maintenance (SYNTHETIC DATA)         *
      * Reads CUSTOMER, validates via CUST002, inserts new customers.  *
      ******************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTCOPY.
       COPY VEHCOPY.
       01 WS-CUST-ID           PIC X(10).
       01 WS-CUST-NAME         PIC X(60).
       01 WS-CUST-TIER         PIC X(01).
       01 WS-VEH-ID            PIC X(12).
      *
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC SQL
               SELECT CUST_NAME, CUST_TIER
               INTO :WS-CUST-NAME, :WS-CUST-TIER
               FROM CUSTOMER
               WHERE CUST_ID = :WS-CUST-ID
           END-EXEC.
           CALL 'CUST002' USING WS-CUST-ID.
           EXEC SQL
               INSERT INTO CUSTOMER
                   (CUST_ID, CUST_NAME, CUST_TIER)
               VALUES
                   (:WS-CUST-ID, :WS-CUST-NAME, :WS-CUST-TIER)
           END-EXEC.
           STOP RUN.
