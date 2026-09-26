       IDENTIFICATION DIVISION.
       PROGRAM-ID. VEH001.
       AUTHOR. SYNTHETIC-DATA.
      ******************************************************************
      * VEH001 - Vehicle lookup and decommission (SYNTHETIC DATA)      *
      * Reads VEHICLE rows and deletes decommissioned vehicles.        *
      ******************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
      *
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY VEHCOPY.
       01 WS-VEH-ID            PIC X(12).
       01 WS-VEH-VIN           PIC X(17).
      *
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC SQL
               SELECT VEH_VIN
               INTO :WS-VEH-VIN
               FROM VEHICLE
               WHERE VEH_ID = :WS-VEH-ID
           END-EXEC.
           EXEC SQL
               DELETE FROM VEHICLE
               WHERE VEH_ID = :WS-VEH-ID
           END-EXEC.
           STOP RUN.
