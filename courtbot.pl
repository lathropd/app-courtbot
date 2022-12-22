#!/usr/bin/env perl


use Modern::Perl;
use String::Util qw(trim);
use WWW::Mechanize;#::PhantomJS;
use HTML::TableExtract;
use Nice::Try;
use Data::Dumper;
use List::MoreUtils qw(arrayify);
use Spreadsheet::ParseXLSX;
use DBD::SQLite;
use DBI qw(:sql_types);
use POSIX;


my $dbh = DBI->connect("dbi:SQLite:filings.sqlite","","");
my $create_table = '
  CREATE TABLE IF NOT EXISTS filings (
    case_number TEXT,
    case_title TEXT,
    event TEXT,
    filed_by TEXT,
    filed TEXT,
    create_date TEXT,
    last_updated TEXT,
    notes TEXT,
    status TEXT,
    unique(case_number, event, filed_by, filed,
           create_date, last_updated, notes)
  );';
$dbh->do($create_table) or die $dbh->errstr;

my $insert = $dbh->prepare('INSERT OR IGNORE INTO filings 
                            (case_number, case_title, 
                             event, filed_by, filed, create_date, 
                             last_updated, notes, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ? )');





my $mech = WWW::Mechanize->new( 
  agent => 'WWW::Mechanize. Email dlathrop@registermedia.com with questions or call (319) 244-8873'
   );



$mech->get("http://httpbin.org/ip");

say $mech->content;
# get William Morris' court case spreadsheet
$mech->get("https://gannett-my.sharepoint.com/:x:/p/lgrundme/EZSlomu-naNFh5RcH6kQrQQBgJHGJ5laxSc6LfTAVNVuoQ?download=1", ':content_file' => "tmp.xlsx");

# open it for reading
my $xlsx_parser = Spreadsheet::ParseXLSX->new;
my $worksheet = $xlsx_parser->parse( "tmp.xlsx" )->worksheet("Active Cases");
my ( $row_min, $row_max ) = $worksheet->row_range;
my ( $col_min, $col_max ) = $worksheet->col_range;

say "opened spreadsheet with $row_max cases.";

say $mech->content;
my @cases_to_check = ();
for (1..$row_max) {
  # $_ is the iteration var
  # get cells for that row and then return from the loop 
  # unless it's a valid case
  my $next_date = $worksheet->get_cell( $_, 2 );
  my $case_num = $worksheet->get_cell( $_, 6 );
  next unless ( $next_date and $case_num );
  next unless ( $next_date->value() );
  next unless ( $case_num->value() =~ m/([A-Z]{4,6}.\d+\s+\([A-Za-z ]+\))/ );
  push( @cases_to_check, uc( $1 ) );
}


$mech->add_header(accept => "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9");




my $te = HTML::TableExtract->new();#keep_html => 1 );

# need to map the raw values to the county-by-county values


# first the list of county codes
# this is from the HTML search form to simplify tracking cases
my %county_codes = ( 'ADAIR' => '05011',
  'ADAMS' => '05021',
  'ALLAMAKEE' => '01031',
  'APPANOOSE' => '08041',
  'AUDUBON' => '04051',
  'BENTON' => '06061',
  'BLACK HAWK' => '01071',
  'BOONE' => '02081',
  'BREMER' => '02091',
  'BUCHANAN' => '01101',
  'BUENA VISTA' => '03111',
  'BUTLER' => '02121',
  'CALHOUN' => '02131',
  'CARROLL' => '02141',
  'CASS' => '04151',
  'CEDAR' => '07161',
  'CERRO GORDO' => '02171',
  'CHEROKEE' => '03181',
  'CHICKASAW' => '01191',
  'CLARKE' => '05201',
  'CLAY' => '03211',
  'CLAYTON' => '01221',
  'CLINTON' => '07231',
  'CRAWFORD' => '03241',
  'DALLAS' => '05251',
  'DAVIS' => '08261',
  'DECATUR' => '05271',
  'DELAWARE' => '01281',
  'DES MOINES' => '08291',
  'DICKINSON' => '03301',
  'DUBUQUE' => '01311',
  'EMMET' => '03321',
  'FAYETTE' => '01331',
  'FLOYD' => '02341',
  'FRANKLIN' => '02351',
  'FREMONT' => '04361',
  'GREENE' => '02371',
  'GRUNDY' => '01381',
  'GUTHRIE' => '05391',
  'HAMILTON' => '02401',
  'HANCOCK' => '02411',
  'HARDIN' => '02421',
  'HARRISON' => '04431',
  'HENRY' => '08441',
  'HOWARD' => '01451',
  'HUMBOLDT' => '02461',
  'IDA' => '03471',
  'IOWA' => '06481',
  'JACKSON' => '07491',
  'JASPER' => '05501',
  'JEFFERSON' => '08511',
  'JOHNSON' => '06521',
  'JONES' => '06531',
  'KEOKUK' => '08541',
  'KOSSUTH' => '03551',
  'LEE (SOUTH)' => '08561',
  'LEE (NORTH)' => '08562',
  'LEE' => '08561',  # looks like this is how Lee County case show up 
  'LINN' => '06571',
  'LOUISA' => '08581',
  'LUCAS' => '05591',
  'LYON' => '03601',
  'MADISON' => '05611',
  'MAHASKA' => '08621',
  'MARION' => '05631',
  'MARSHALL' => '02641',
  'MILLS' => '04651',
  'MITCHELL' => '02661',
  'MONONA' => '03671',
  'MONROE' => '08681',
  'MONTGOMERY' => '04691',
  'MUSCATINE' => '07701',
  'OBRIEN' => '03711',
  'OSCEOLA' => '03721',
  'PAGE' => '04731',
  'PALO ALTO' => '03741',
  'PLYMOUTH' => '03751',
  'POCAHONTAS' => '02761',
  'POLK' => '05771',
  'POTTAWATTAMIE' => '04781',
  'POWESHIEK' => '08791',
  'RINGGOLD' => '05801',
  'SAC' => '02811',
  'SCOTT' => '07821',
  'SHELBY' => '04831',
  'SIOUX' => '03841',
  'STORY' => '02851',
  'TAMA' => '06861',
  'TAYLOR' => '05871',
  'UNION' => '05881',
  'VAN BUREN' => '08891',
  'WAPELLO' => '08901',
  'WARREN' => '05911',
  'WASHINGTON' => '08921',
  'WAYNE' => '05931',
  'WEBSTER' => '02941',
  'WINNEBAGO' => '02951',
  'WINNESHIEK' => '01961',
  'WOODBURY' => '03971',
  'WORTH' => '02981',
  'WRIGHT' => '02991' );

# say Dumper($county_codes{'POLK'});



my @case_list = map {
  $_ =~ m/(.+)\s+\((.+)\)/;
  #say $1, "\t", $2;
  #say "*$2*";
  my $county_code = $county_codes{$2};
  "$county_code $1";
} @cases_to_check;

# print current time
say STDERR strftime("%F %T", localtime);



# go to the login page
# need to work on making this try multiple accounts
my $login = 'https://www.iowacourts.state.ia.us/ESAWebApp/ESALogin.jsp';
$mech->get( $login );
say STDERR "submit login";
$mech->form_number(1);
$mech->field("userid",   $ENV{'COURTBOT_USER'});       # move to environment var
$mech->field("password", $ENV{'COURTBOT_PASSWORD'});   # move to environment var
$mech->submit;

$mech->update_html( $mech->content(charset => "ISO-8859-1") );
say STDERR $mech->text;

# check if logged in, there should be a log off option
# eventually this needs to be robustified to retry

unless ($mech->content =~ /Login Error/) {
  say STDERR "login success";
  sleep rand(2);   
  try {
    for my $case (@case_list) {
      try {
        say $case;
        sleep 1 + rand(5);        
        # say STDERR "# open main page";
        $mech->get("https://www.iowacourts.state.ia.us/");
        $mech->get("https://www.iowacourts.state.ia.us/ESAWebApp/DefaultFrame");
        $mech->update_html( $mech->content(charset => "ISO-8859-1") );
        $mech->follow_link(text=> "Click Here to Search");
        $mech->update_html( $mech->content(charset => "ISO-8859-1") );
        $mech->follow_link( name => "main" );
        $mech->update_html( $mech->content(charset => "ISO-8859-1") );
        $mech->follow_link( url => '/ESAWebApp/TrialSimpFrame' );
        $mech->update_html( $mech->content(charset => "ISO-8859-1") );
        $mech->follow_link( name => 'main' );
        $mech->update_html( $mech->content(charset => "ISO-8859-1") );
        sleep rand(3);
        # say $mech->content;
        if ($case =~ qr/(\d{5})(.*)(\w\w)(\w\w\d{6})/) {
          say STDERR "case: $case";
          # say STDERR "1: $1\n2: $2\n3: $3\n4: $4\n"; 
                  
          # submit search form with case info
          $mech->form_name("TrailCourtStateWide"); 
          $mech->field("caseid1", $1);            # county
          $mech->field("caseid2", trim($2));      # city
          $mech->field("caseid3", $3);            # case type
          $mech->field("caseid4", $4);            # case number (including CR/CV/etc)
          $mech->field("searchtype", "C");        # set as a case# search
          sleep rand(2);
          $mech->submit;
          try { 
            $mech->update_html( $mech->content(charset => "ISO-8859-1") );
          } catch ($e) {
            say $e;
            sleep rand(60);
            next;
          }
          # click into the case
          # in the browser this happens with a javascript-initiated form post
          $mech->content =~ qr/mySubmit\(\'(\d{5})(..)(..)(..\d{6})\,\'(.*)\'\)'/;
          my $caseid = "$1$2$3$4";
          try {
            $mech->form_name('TrialForm');
            $mech->field("caseid", $caseid);
            $mech->submit;
            $mech->update_html( $mech->content(charset => "ISO-8859-1") );
            
            # go to the banner frame
            $mech->follow_link( name => "banner" );
            $mech->update_html( $mech->content(charset => "ISO-8859-1") );
            # go to the filings frame
            # $mech->delete_header( 'cookie2' );
            $mech->follow_link( text => "Filings");
            $mech->update_html( $mech->content(charset => "UTF-8") );
            # say $mech->content;
            # grab the table of filings
            # note: document links are supressed in these requests. possibly a 
            # user agent thing? Anyhow worth being aware of. 
            $te = HTML::TableExtract->new();      
            $te->parse($mech->content);
            $te->first_table_found;

            # grab the table rows
            $te->rows;
          } catch ($e) {
             say STDERR "Problem getting case details:\n $e";
             sleep rand(60);
             next;
          }
          my @rows = $te->rows;
          my @case_info = @{shift(@rows)};     # first row is the case info
          $case_info[0] =~ m/Title: (.*)\n/;
          my $case_title = $1;
                    
          my @headers = @{shift(@rows)};       # second row is the headers

           # map rows into records
           my @records = [];

           my @record = []; 
           for (@rows) {
             my @cells = map {trim $_||0 } @{$_};
             if ($cells[1]) {
               $records[6] = trim( $records[6] );
               push( @records, [@record] );  
               $cells[6] = "";
               @record = @cells;
             } elsif ($record[6]) {
               $record[6] = "$record[6] $cells[0] ";
             } else {
               $record[6] = $cells[0];
             }
          }
           #say Dumper( @records ); 
          for (@records) {
             if ($_) {
                my @event = arrayify @{$_};
                my $count = @event;
                if ( $event[0] ) {
                   push  @event, ($caseid, $case_title);
                   # say join("|", @event);
                   $insert->execute( $caseid, $case_title, 
                                     $event[0], $event[1], $event[2],
                                     $event[3], $event[4], $event[6],
                                     'new');
                }
              }
            }
          }
      } catch ($e) {
        say STDERR "problem with a download:\n $e";
        sleep rand(60); 
      }     
    }

    $dbh->disconnect;
  } catch ( $e) {
    say STDERR "error: $e";
    sleep rand(60);
  }

 

  say STDERR "log out";
  $mech->get("https://www.iowacourts.state.ia.us/ESAWebApp/TrialCourtStateWide");
  $mech->form_name("logoffForm");
  $mech->submit;
  say STDERR "logged out";
  say STDERR strftime("%F %T", localtime);
} else {
  say STDERR "no logoff form";
  say STDERR "try again in 15 minutes"; # needs to be implemented
  say STDERR "log out just in case";
  $mech->get("https://www.iowacourts.state.ia.us/ESAWebApp/TrialCourtStateWide");
  $mech->form_name("logoffForm");
  $mech->submit;
  say STDERR "logged out";
  say STDERR strftime("%F %T", localtime);
} 
__DATA__
try {
  my $header  = `cat header.html`;
  my $rows = `cat table2.sql | sqlite3 -html -header filings.sqlite`;
  my $update = `cat update_query.sql | sqlite3 filings.sqlite`;
  my $emails = 'wrmorris2@registermedia.com,
                metroia@registermedia.com,
                pjoens@registermedia.com, 
                dlathrop@registermedia.com,
                ccrowder@registermedia.com';

  my $message = "$header\n$rows\n</table>";
  my ( $smtp, $error ) = Email::Send::SMTP::Gmail->new( 
                                      -smtp    => 'smtp.gmail.com',
                                      -login   => $ENV{'GMAIL_USER'},
                                      -pass    => $ENV{'GMAIL_PWD'});

  print "session error: $error" unless ($smtp!=-1);


  $smtp->send(
    -to=>$emails,
    -subject=>'Court bot results (ignore, this is a test)', 
    -body=>"<html><head></head>
      <body>
      <p>Recent filings</p>
      $message
      <p>
      <small>Brought to you by Daniel Lathrop and the letter p.</small></p>
      </body>
      </html>",
    -contenttype => 'text/html');

  $smtp->bye;
} catch ($e) {
  say "SQLite Query or e-mail failed";
}
