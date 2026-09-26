       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUST002.
       AUTHOR. SYNTHETIC-DATA.
      ******************************************************************
      * CUST002 - Customer inquiry/validation (SYNTHETIC DATA)         *
      * Read-only: looks up CUSTOMER and the customer's VEHICLE rows.  *
      ******************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTCOPY.
       01 WS-CUST-ID           PIC X(10).
       01 WS-CUST-NAME         PIC X(60).
       01 WS-VEH-VIN           PIC X(17).
      *
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC SQL
               SELECT CUST_NAME
               INTO :WS-CUST-NAME
               FROM CUSTOMER
               WHERE CUST_ID = :WS-CUST-ID
           END-EXEC.
           EXEC SQL
               SELECT VEH_VIN
               INTO :WS-VEH-VIN
               FROM VEHICLE
               WHERE VEH_OWNER = :WS-CUST-ID
           END-EXEC.
           STOP RUN.
