//+------------------------------------------------------------------+
//| ExportMagicNumbers.mq5                                           |
//|                                                                  |
//| Uloží magic number všech pozic z historie účtu do CSV, které     |
//| generátor reportů (report.py) použije k rozdělení obchodů podle  |
//| strategií. Standardní export historie MT5 magic number nemá.     |
//|                                                                  |
//| Výstup: <datová složka terminálu>\MQL5\Files\MagicNumbers-<účet>.csv
//| Formát: position;magic;symbol;time                               |
//+------------------------------------------------------------------+
#property copyright   "forex-MT5-report"
#property version     "1.00"
#property description "Uloží magic number všech pozic z historie účtu do MQL5\\Files\\MagicNumbers-<účet>.csv"
#property script_show_inputs

// Začátek historie, od kterého se obchody exportují (výchozí: celá historie)
input datetime InpFrom = D'1970.01.01 00:00';

//+------------------------------------------------------------------+
//| Vstupní bod skriptu: projde vstupní obchody historie a ke každé  |
//| pozici zapíše magic number obchodu, který ji otevřel.            |
//+------------------------------------------------------------------+
void OnStart()
  {
   long   login    = AccountInfoInteger(ACCOUNT_LOGIN);
   string fileName = StringFormat("MagicNumbers-%I64d.csv", login);

   // Načtení historie do mezipaměti terminálu; konec s rezervou jednoho dne,
   // aby se nevynechaly obchody uzavřené v posledních vteřinách
   if(!HistorySelect(InpFrom, TimeCurrent() + 86400))
     {
      Alert("ExportMagicNumbers: historii obchodů se nepodařilo načíst (chyba ", GetLastError(), ").");
      return;
     }

   // Textový soubor v UTF-8: FILE_ANSI s kódovou stránkou CP_UTF8 zapisuje
   // řetězce bez převodu do UTF-16, který je pro FILE_TXT výchozí
   int handle = FileOpen(fileName, FILE_WRITE | FILE_TXT | FILE_ANSI, ';', CP_UTF8);
   if(handle == INVALID_HANDLE)
     {
      Alert("ExportMagicNumbers: soubor ", fileName, " nelze vytvořit (chyba ", GetLastError(), ").");
      return;
     }
   FileWriteString(handle, "position;magic;symbol;time\r\n");

   // Zapisujeme jen vstupní obchody: magic number pozice je magic number
   // obchodu, který ji otevřel (uzavírací obchod má při ručním zavření
   // magic 0). Pozice navyšovaná dalším vstupem se objeví vícekrát –
   // report pak použije první řádek.
   int total   = HistoryDealsTotal();
   int written = 0;
   for(int i = 0; i < total; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;

      // Vklady, výběry a jiné neobchodní pohyby nemají pozici – přeskočíme je
      ENUM_DEAL_TYPE type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL)
         continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_IN && entry != DEAL_ENTRY_INOUT)
         continue;

      ulong    position = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      ulong    magic    = (ulong)HistoryDealGetInteger(deal, DEAL_MAGIC);
      string   symbol   = HistoryDealGetString(deal, DEAL_SYMBOL);
      datetime time     = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);

      FileWriteString(handle, StringFormat("%I64u;%I64u;%s;%s\r\n", position, magic, symbol,
                                           TimeToString(time, TIME_DATE | TIME_SECONDS)));
      written++;
     }
   FileClose(handle);

   // Uživateli oznámíme, kam soubor uložit dál – vedle exportu ReportHistory-*.xlsx
   // ho report najde sám
   string path = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\" + fileName;
   PrintFormat("ExportMagicNumbers: zapsáno %d vstupních obchodů do %s", written, path);
   Alert("ExportMagicNumbers: zapsáno ", written, " vstupních obchodů do ", path,
         ". Zkopírujte soubor vedle exportu ReportHistory-", login, ".xlsx.");
  }
//+------------------------------------------------------------------+
