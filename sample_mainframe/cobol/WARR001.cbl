       IDENTIFICATION DIVISION.
       PROGRAM-ID. WARR001.
       AUTHOR. SYNTHETIC-DATA.
      ******************************************************************
      * WARR001 - Warranty claim registration (SYNTHETIC DATA)         *
      * Uses WARRCOPY + CUSTCOPY, validates customer via CUST002,      *
      * reads and inserts WARRANTY rows.                               *
      ******************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY WARRCOPY.
       COPY CUSTCOPY.
       01 WS-WARRANTY-ID       PIC X(12).
       01 WS-WARRANTY-STATUS   PIC X(02).
       01 WS-CUST-ID           PIC X(10).
      *
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'CUST002' USING WS-CUST-ID.
           EXEC SQL
               SELECT WARRANTY_STATUS
               INTO :WS-WARRANTY-STATUS
               FROM WARRANTY
               WHERE WARRANTY_ID = :WS-WARRANTY-ID
           END-EXEC.
           EXEC SQL
               INSERT INTO WARRANTY
                   (WARRANTY_ID, WARRANTY_STATUS, CUST_ID)
               VALUES
                   (:WS-WARRANTY-ID, :WS-WARRANTY-STATUS, :WS-CUST-ID)
           END-EXEC.
           STOP RUN.
