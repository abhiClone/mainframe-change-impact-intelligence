       IDENTIFICATION DIVISION.
       PROGRAM-ID. WARR002.
       AUTHOR. SYNTHETIC-DATA.
      ******************************************************************
      * WARR002 - Warranty batch validation (SYNTHETIC DATA)           *
      * Updates WARRANTY statuses, cross-checks the vehicle via VEH001, *
      * and writes an audit row to CLAIM_HISTORY.                      *
      ******************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY WARRCOPY.
       01 WS-WARRANTY-ID       PIC X(12).
       01 WS-VEH-ID            PIC X(12).
      *
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'VEH001' USING WS-VEH-ID.
           EXEC SQL
               UPDATE WARRANTY
               SET WARRANTY_STATUS = 'AP'
               WHERE WARRANTY_ID = :WS-WARRANTY-ID
           END-EXEC.
           EXEC SQL
               INSERT INTO CLAIM_HISTORY
                   (WARRANTY_ID, ACTION_CODE, ACTION_TS)
               VALUES
                   (:WS-WARRANTY-ID, 'APPR', CURRENT TIMESTAMP)
           END-EXEC.
           STOP RUN.
