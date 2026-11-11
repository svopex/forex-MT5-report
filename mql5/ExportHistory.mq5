//+------------------------------------------------------------------+
//| ExportHistory.mq5                                                |
//|                                                                  |
//| Uloží kompletní historii obchodů účtu do CSV, ze kterého         |
//| generátor reportů (report.py) vytváří report. Na rozdíl od       |
//| exportu historie v MT5 obsahuje u obchodů i číslo pozice a magic |
//| number, podle kterého report dělí obchody na strategie.          |
//|                                                                  |
//| Výstup: <InpOutputDir>\ReportHistory-<účet>.csv, a není-li adresář |
//|         zadán nebo přesun selže, <data>\MQL5\Files\ReportHistory-<účet>.csv
//| Formát: popsán ve forexreport/mt5_parser.py                      |
//+------------------------------------------------------------------+
#property copyright   "forex-MT5-report"
#property version     "2.00"
#property description "Uloží historii obchodů účtu do ReportHistory-<účet>.csv v adresáři projektu (bez něj do MQL5\\Files)"
#property script_show_inputs

// MQL5 smí zapisovat jen do sandboxu MQL5\Files; do adresáře projektu se
// hotový soubor přesune funkcí Windows. Volá se jen při povoleném importu DLL.
#import "kernel32.dll"
int MoveFileExW(string existingFileName, string newFileName, uint flags);
#import

#define MOVEFILE_REPLACE_EXISTING 0x1
#define MOVEFILE_COPY_ALLOWED     0x2

// Verze formátu CSV; musí odpovídat SUPPORTED_FORMAT ve forexreport/mt5_parser.py
#define CSV_FORMAT "1"

// Adresář, kam se CSV přesune (adresář projektu); prázdný = zůstane
// v MQL5\Files. Instalace přes scripts\deploy.cmd sem doplní adresář projektu.
input string InpOutputDir = "";

//+------------------------------------------------------------------+
//| Vstupní bod skriptu: zapíše údaje o účtu a všechny obchody       |
//| historie a soubor přesune do adresáře projektu.                  |
//+------------------------------------------------------------------+
void OnStart()
  {
   long   login    = AccountInfoInteger(ACCOUNT_LOGIN);
   string fileName = StringFormat("ReportHistory-%I64d.csv", login);

   // Celá historie účtu – report z ní odvozuje počáteční kapitál (první vklad).
   // Konec s rezervou jednoho dne, aby se nevynechaly obchody posledních vteřin.
   if(!HistorySelect(0, TimeCurrent() + 86400))
     {
      Alert("ExportHistory: historii obchodů se nepodařilo načíst (chyba ", GetLastError(), ").");
      return;
     }

   // Textový soubor v UTF-8: FILE_ANSI s kódovou stránkou CP_UTF8 zapisuje
   // řetězce bez převodu do UTF-16, který je pro FILE_TXT výchozí
   int handle = FileOpen(fileName, FILE_WRITE | FILE_TXT | FILE_ANSI, ';', CP_UTF8);
   if(handle == INVALID_HANDLE)
     {
      Alert("ExportHistory: soubor ", fileName, " nelze vytvořit (chyba ", GetLastError(), ").");
      return;
     }
   WriteAccount(handle, login);
   int written = WriteDeals(handle);
   FileClose(handle);

   // Bez zadaného InpOutputDir nebo při neúspěšném přesunu zůstane soubor
   // v MQL5\Files a uživatel ho musí zkopírovat do adresáře projektu sám
   string path    = TerminalInfoString(TERMINAL_DATA_PATH) + "\\MQL5\\Files\\" + fileName;
   string problem = "";
   string hint    = "";
   if(InpOutputDir == "" || !MoveToOutputDir(path, fileName, problem))
     {
      if(problem != "")
         hint = " " + problem + ".";
      hint += " Zkopírujte soubor do adresáře generátoru reportů.";
     }

   string message = StringFormat("ExportHistory: zapsáno %d obchodů do %s.%s", written, path, hint);
   Print(message);
   Alert(message);
  }

//+------------------------------------------------------------------+
//| Zapíše hlavičku s údaji o účtu ve tvaru klíč;hodnota, ukončenou  |
//| prázdným řádkem.                                                 |
//| handle - otevřený CSV soubor                                     |
//| login  - číslo účtu                                              |
//+------------------------------------------------------------------+
void WriteAccount(const int handle, const long login)
  {
   ENUM_ACCOUNT_TRADE_MODE  tradeMode  = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   ENUM_ACCOUNT_MARGIN_MODE marginMode = (ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE);

   // Typ účtu a režim pozic pojmenujeme stejně jako hlavička reportu v MT5,
   // např. "498754 (USD, FTTrading-Server, demo, Hedge)"
   string tradeModeName  = tradeMode == ACCOUNT_TRADE_MODE_DEMO ? "demo"
                         : tradeMode == ACCOUNT_TRADE_MODE_CONTEST ? "contest" : "real";
   string marginModeName = marginMode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "Hedge"
                         : marginMode == ACCOUNT_MARGIN_MODE_RETAIL_NETTING ? "Netting" : "Exchange";

   FileWriteString(handle, "# forex-MT5-report – historie obchodů z MetaTraderu 5 (mql5/ExportHistory.mq5)\r\n");
   WriteMeta(handle, "format", CSV_FORMAT);
   WriteMeta(handle, "login", IntegerToString(login));
   WriteMeta(handle, "name", AccountInfoString(ACCOUNT_NAME));
   WriteMeta(handle, "company", AccountInfoString(ACCOUNT_COMPANY));
   WriteMeta(handle, "server", AccountInfoString(ACCOUNT_SERVER));
   WriteMeta(handle, "currency", AccountInfoString(ACCOUNT_CURRENCY));
   WriteMeta(handle, "trade_mode", tradeModeName);
   WriteMeta(handle, "margin_mode", marginModeName);
   WriteMeta(handle, "balance", Number(AccountInfoDouble(ACCOUNT_BALANCE)));
   WriteMeta(handle, "exported", TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS));
   FileWriteString(handle, "\r\n");
  }

//+------------------------------------------------------------------+
//| Zapíše jeden řádek hlavičky ve tvaru klíč;hodnota.               |
//+------------------------------------------------------------------+
void WriteMeta(const int handle, const string key, const string value)
  {
   FileWriteString(handle, key + ";" + CsvText(value) + "\r\n");
  }

//+------------------------------------------------------------------+
//| Zapíše tabulku všech obchodů historie včetně vkladů a výběrů.    |
//| Pozice z nich sestaví až report podle čísla pozice.              |
//| Vrací počet zapsaných obchodů.                                   |
//+------------------------------------------------------------------+
int WriteDeals(const int handle)
  {
   FileWriteString(handle, "time;deal;order;position;type;entry;symbol;volume;price;sl;tp;"
                   "commission;fee;swap;profit;magic;comment\r\n");

   int total   = HistoryDealsTotal();
   int written = 0;
   for(int i = 0; i < total; i++)
     {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;

      // Typ a směr jako krátké názvy: DEAL_TYPE_BUY -> buy, DEAL_ENTRY_OUT_BY -> out_by
      string type  = EnumName(EnumToString((ENUM_DEAL_TYPE)HistoryDealGetInteger(deal, DEAL_TYPE)), "DEAL_TYPE_");
      string entry = EnumName(EnumToString((ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY)), "DEAL_ENTRY_");

      // U výstupního obchodu jsou SL/TP úrovně pozice v okamžiku uzavření
      string line = StringFormat("%s;%I64u;%I64u;%I64u;%s;%s;%s;%s;%s;%s;%s;%s;%s;%s;%s;%I64d;%s\r\n",
                                 TimeToString((datetime)HistoryDealGetInteger(deal, DEAL_TIME), TIME_DATE | TIME_SECONDS),
                                 deal,
                                 (ulong)HistoryDealGetInteger(deal, DEAL_ORDER),
                                 (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID),
                                 type,
                                 entry,
                                 CsvText(HistoryDealGetString(deal, DEAL_SYMBOL)),
                                 Number(HistoryDealGetDouble(deal, DEAL_VOLUME)),
                                 Number(HistoryDealGetDouble(deal, DEAL_PRICE)),
                                 Number(HistoryDealGetDouble(deal, DEAL_SL)),
                                 Number(HistoryDealGetDouble(deal, DEAL_TP)),
                                 Number(HistoryDealGetDouble(deal, DEAL_COMMISSION)),
                                 Number(HistoryDealGetDouble(deal, DEAL_FEE)),
                                 Number(HistoryDealGetDouble(deal, DEAL_SWAP)),
                                 Number(HistoryDealGetDouble(deal, DEAL_PROFIT)),
                                 HistoryDealGetInteger(deal, DEAL_MAGIC),
                                 CsvText(HistoryDealGetString(deal, DEAL_COMMENT)));
      FileWriteString(handle, line);
      written++;
     }
   return written;
  }

//+------------------------------------------------------------------+
//| Z názvu hodnoty výčtu odstraní prefix a převede ho na malá       |
//| písmena, např. ("DEAL_TYPE_BALANCE", "DEAL_TYPE_") -> "balance".  |
//+------------------------------------------------------------------+
string EnumName(string name, const string prefix)
  {
   StringReplace(name, prefix, "");
   StringToLower(name);
   return name;
  }

//+------------------------------------------------------------------+
//| Číslo s desetinnou tečkou bez nevýznamných nul na konci          |
//| (8 desetinných míst stačí pro ceny, objemy i částky).            |
//+------------------------------------------------------------------+
string Number(const double value)
  {
   string text   = DoubleToString(value, 8);
   int    length = StringLen(text);
   while(StringGetCharacter(text, length - 1) == '0')
      length--;
   if(StringGetCharacter(text, length - 1) == '.')
      length--;
   return StringSubstr(text, 0, length);
  }

//+------------------------------------------------------------------+
//| Textová hodnota pro CSV: obsahuje-li středník, uvozovky nebo     |
//| konec řádku, dá se do uvozovek a vnitřní uvozovky se zdvojí.     |
//+------------------------------------------------------------------+
string CsvText(string text)
  {
   if(StringFind(text, ";") < 0 && StringFind(text, "\"") < 0 &&
      StringFind(text, "\n") < 0 && StringFind(text, "\r") < 0)
      return text;
   StringReplace(text, "\"", "\"\"");
   return "\"" + text + "\"";
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
