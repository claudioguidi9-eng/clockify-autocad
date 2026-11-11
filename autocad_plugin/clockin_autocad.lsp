;;; ============================================================================
;;; CLOCKIN AUTOCAD PLUGIN (clockin_autocad.lsp)
;;; Como usar no AutoCAD (Opcional, pois o servidor ja detecta a janela sozinho):
;;; 1. Digite APPLOAD no AutoCAD e carregue este arquivo (ou adicione na Maleta/Startup Suite).
;;; 2. Comandos adicionados no AutoCAD:
;;;    - CLOCKIN       : Abre o Painel Web de Horas por Projeto no navegador.
;;;    - CLOCKINPING   : Sincroniza manualmente o desenho .DWG atual com o painel.
;;; ============================================================================

(vl-load-com)

(defun ClockIn:SendEvent (eventType / dwgName http url payload)
  (setq dwgName (getvar "DWGNAME"))
  (setq url "http://localhost:8765/api/autocad/ping")
  (setq payload (strcat "{\"dwg_file\":\"" dwgName "\",\"event\":\"" eventType "\"}"))
  (vl-catch-all-apply
    '(lambda ()
       (setq http (vlax-create-object "MSXML2.ServerXMLHTTP"))
       (vlax-invoke-method http 'Open "POST" url :vlax-false)
       (vlax-invoke-method http 'setRequestHeader "Content-Type" "application/json")
       (vlax-invoke-method http 'Send payload)
       (vlax-release-object http)
     )
  )
  (princ)
)

(defun c:CLOCKIN ()
  (ClockIn:SendEvent "OPEN_PANEL")
  (startapp "explorer" "http://localhost:8765")
  (princ "\n[ClockIn AutoCAD] Painel de Horas por Projeto aberto no navegador!")
  (princ)
)

(defun c:CLOCKINPING ()
  (ClockIn:SendEvent "MANUAL_PING")
  (princ (strcat "\n[ClockIn AutoCAD] Desenho sincronizado: " (getvar "DWGNAME")))
  (princ)
)

;; Sincroniza automaticamente ao carregar o desenho no AutoCAD
(ClockIn:SendEvent "DWG_OPENED")
(princ "\n[ClockIn AutoCAD] Plugin ativo! Digite CLOCKIN para abrir o painel de horas.")
(princ)
