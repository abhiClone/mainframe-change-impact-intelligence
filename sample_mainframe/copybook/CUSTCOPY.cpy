      ******************************************************************
      * CUSTCOPY - Customer master record layout (SYNTHETIC DATA)      *
      * Used by customer maintenance and inquiry programs.             *
      ******************************************************************
       01  CUST-RECORD.
           05  CUST-ID            PIC X(10).
           05  CUST-NAME          PIC X(60).
           05  CUST-TIER          PIC X(01).
               88  TIER-GOLD      VALUE 'G'.
               88  TIER-SILVER    VALUE 'S'.
               88  TIER-BRONZE    VALUE 'B'.
           05  CUST-REGION        PIC X(03).
           05  CUST-SINCE-DATE    PIC 9(08).
