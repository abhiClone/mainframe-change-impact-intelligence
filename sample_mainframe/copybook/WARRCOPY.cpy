      ******************************************************************
      * WARRCOPY - Warranty claim record layout (SYNTHETIC DATA)       *
      * Shared by warranty registration and batch validation programs. *
      ******************************************************************
       01  WARR-RECORD.
           05  WARRANTY-ID        PIC X(12).
           05  WARRANTY-STATUS    PIC X(02).
               88  STATUS-OPEN    VALUE 'OP'.
               88  STATUS-APPR    VALUE 'AP'.
               88  STATUS-DENIED  VALUE 'DN'.
           05  CLAIM-AMOUNT       PIC 9(09)V99.
           05  CLAIM-DATE         PIC 9(08).
           05  VEH-ID             PIC X(12).
