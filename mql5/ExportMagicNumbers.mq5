//+------------------------------------------------------------------+
//| ExportMagicNumbers.mq5                                           |
//|                                                                  |
//| Uloží magic number všech pozic z historie účtu do CSV, které     |
//| generátor reportů (report.py) použije k rozdělení obchodů podle  |
//| strategií. Standardní export historie MT5 magic number nemá.     |
//|                                                                  |
//| Výstup: <InpOutputDir>\MagicNumbers-<účet>.csv, a není-li adresář  |
//|         zadán nebo přesun selže, <data>\MQL5\Files\MagicNumbers-<účet>.csv
//| Formát: position;magic;symbol;time                               |
//+------------------------------------------------------------------+
#property copyright   "forex-MT5-report"
#property version     "1.10"
#property description "Uloží magic number všech pozic z historie účtu do MagicNumbers-<účet>.csv v adresáři projektu (bez něj do MQL5\\Files)"
#property script_show_inputs

// MQL5 smí zapisovat jen do sandboxu MQL5\Files; do adresáře projektu se
// hotový soubor přesune funkcí Windows. Volá se jen při povoleném importu DLL.
#import "kernel32.dll"
int MoveFileExW(string existingFileName, string newFileName, uint flags);
#import

#define MOVEFILE_REPLACE_EXISTING 0x1
#define MOVEFILE_COPY_ALLOWED     0x2

// Začátek historie, od kterého se obchody exportují (výchozí: celá historie)
input datetime InpFrom = D'1970.01.01 00:00';
// Adresář, kam se CSV přesune (vedle ReportHistory-*.xlsx); prázdný = zůstane
// v MQL5\Files. Instalace přes scripts\deploy.cmd sem doplní adresář projektu.
input string   InpOutputDir = "";

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

   // Bez zadaného InpOutputDir nebo při neúspěšném přesunu zůstane soubor
   // v MQL5\Files a uživatel ho musí zkopírovat vedle exportu historie sám;
   // po přesunu leží vedle ReportHistory-*.xlsx a report ho najde sám
   string path    = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\" + fileName;
   string problem = "";
   string hint    = "";
   if(InpOutputDir == "" || !MoveToOutputDir(path, fileName, problem))
     {
      if(problem != "")
         hint = " " + problem + ".";
      hint += StringFormat(" Zkopírujte soubor vedle exportu ReportHistory-%I64d.xlsx.", login);
     }

   string message = StringFormat("ExportMagicNumbers: zapsáno %d vstupních obchodů do %s.%s", written, path, hint);
   Print(message);
   Alert(message);
  }

//+------------------------------------------------------------------+
//| Přesune hotové CSV ze sandboxu MQL5\Files do InpOutputDir.       |
//| path     - vstup: úplná cesta k souboru v MQL5\Files;            |
//|            při úspěchu se přepíše na cílovou cestu               |
//| fileName - název souboru v cílovém adresáři                      |
//| problem  - při neúspěchu důvod, proč soubor zůstal v MQL5\Files  |
//| Vrací true, pokud byl soubor přesunut.                           |
//+------------------------------------------------------------------+
bool MoveToOutputDir(string &path, const string fileName, string &problem)
  {
   // Bez povoleného importu DLL by volání kernel32 skript ukončilo kritickou chybou
   if(!MQLInfoInteger(MQL_DLLS_ALLOWED))
     {
      problem = "Do adresáře " + InpOutputDir + " ho nelze přesunout bez povolení importu DLL "
                + "(záložka Závislosti při spuštění skriptu)";
      return false;
     }

   // Přepíše starší export; COPY_ALLOWED umožní přesun i na jiný disk.
   // Koncové lomítko v InpOutputDir nevadí – Windows zdvojené "\\" v cestě sloučí.
   string target = InpOutputDir + "\\" + fileName;
   if(MoveFileExW(path, target, MOVEFILE_REPLACE_EXISTING | MOVEFILE_COPY_ALLOWED) == 0)
     {
      problem = "Přesun do " + target + " selhal – adresář neexistuje nebo je soubor otevřený "
                + "(např. v Excelu)";
      return false;
     }
   path = target;
   return true;
  }
//+------------------------------------------------------------------+
