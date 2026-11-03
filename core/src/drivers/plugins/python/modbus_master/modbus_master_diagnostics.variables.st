(* Diagnostic variables: add as located globals in OpenPLC Editor. *)
VAR_GLOBAL
    (* MB0: DO1, io_points[0] *)
    MB0_CommOK AT %MX100.0 : BOOL;
    MB0_ResponseOK AT %MX100.1 : BOOL;
    MB0_Status AT %MW100 : UINT;
    MB0_LastError AT %MW101 : UINT;
    MB0_SuccessCount AT %MD100 : UDINT;
    MB0_ErrorCount AT %MD101 : UDINT;
    MB0_ConsecutiveErrors AT %MD102 : UDINT;
    MB0_AgeMs AT %MD103 : UDINT;
    MB0_UpdateCounter AT %MD104 : UDINT;
END_VAR
