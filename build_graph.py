"""Convert the generated flight table to an RDF graph."""
import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, RDFS, XSD

EX = Namespace("http://example.org/mkr/")


def node(kind, name):
    return EX[f"{kind}/{quote(name.strip().replace(' ', '_'), safe='-_')}"]


def build_graph(csv_path, params_path):
    params = json.loads(params_path.read_text(encoding="utf-8"))
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        flights = {}
        for row in csv.DictReader(source):
            row["flight_id"] = row["flight_id"].strip().upper()
            for field in ("from_city", "to_city"):
                row[field] = row[field].strip().title()
            for field in ("airline", "from_country", "to_country"):
                row[field] = row[field].strip()
            flights.setdefault(row["flight_id"], row)

    graph = Graph()
    graph.bind("ex", EX)
    for name in ("Flight", "Airline", "City", "Country", "BudgetFlight", "LongFlight"):
        graph.add((EX[name], RDF.type, RDFS.Class))
    for name in ("BudgetFlight", "LongFlight"):
        graph.add((EX[name], RDFS.subClassOf, EX.Flight))
    properties = {
        "operatedBy": (EX.Flight, EX.Airline),
        "departsFrom": (EX.Flight, EX.City),
        "arrivesAt": (EX.Flight, EX.City),
        "locatedIn": (EX.City, EX.Country),
        "departureDate": (EX.Flight, XSD.date),
        "durationMin": (EX.Flight, XSD.integer),
        "priceEur": (EX.Flight, XSD.decimal),
        "hasDelayMinutes": (EX.Flight, XSD.integer),
        "reportedBy": (RDF.Statement, RDFS.Resource),
        "fromBusyCountry": (EX.Flight, XSD.boolean),
    }
    for name, (domain, range_) in properties.items():
        graph.add((EX[name], RDF.type, RDF.Property))
        graph.add((EX[name], RDFS.domain, domain))
        graph.add((EX[name], RDFS.range, range_))

    departures = Counter(row["from_country"] for row in flights.values())
    for fid, row in flights.items():
        flight = node("flight", fid)
        airline = node("airline", row["airline"])
        graph.add((airline, RDF.type, EX.Airline))
        graph.add((airline, RDFS.label, Literal(row["airline"], lang="en")))
        graph.add((flight, EX.operatedBy, airline))
        for direction, predicate in (("from", EX.departsFrom), ("to", EX.arrivesAt)):
            city = node("city", row[f"{direction}_city"])
            country = node("country", row[f"{direction}_country"])
            graph.add((flight, predicate, city))
            graph.add((city, RDF.type, EX.City))
            graph.add((city, RDFS.label, Literal(row[f"{direction}_city"], lang="en")))
            graph.add((city, EX.locatedIn, country))
            graph.add((country, RDF.type, EX.Country))
            graph.add((country, RDFS.label, Literal(row[f"{direction}_country"], lang="en")))
        raw_date = row["dep_date"].strip()
        date = datetime.strptime(raw_date, "%d.%m.%Y" if "." in raw_date else "%Y-%m-%d").date()
        duration = int(row["duration_min"])
        graph.add((flight, EX.departureDate, Literal(date, datatype=XSD.date)))
        graph.add((flight, EX.durationMin, Literal(duration, datatype=XSD.integer)))
        types = []
        if row["price_eur"].strip():
            price = Decimal(row["price_eur"].strip())
            graph.add((flight, EX.priceEur, Literal(price, datatype=XSD.decimal)))
            if price <= Decimal(str(params["budget_threshold_eur"])):
                types.append(EX.BudgetFlight)
        if duration >= params["long_flight_min"]:
            types.append(EX.LongFlight)
        for type_ in types or [EX.Flight]:
            graph.add((flight, RDF.type, type_))
        delay = re.search(r"delay=(\d+);by=([^;]+)", row["note"])
        if delay:
            statement = node("stmt", f"{fid}-delay")
            graph.add((statement, RDF.type, RDF.Statement))
            graph.add((statement, RDF.subject, flight))
            graph.add((statement, RDF.predicate, EX.hasDelayMinutes))
            graph.add((statement, RDF.object, Literal(int(delay[1]), datatype=XSD.integer)))
            graph.add((statement, EX.reportedBy, node("source", delay[2])))
        if departures[row["from_country"]] >= 2:
            graph.add((flight, EX.fromBusyCountry, Literal(True, datatype=XSD.boolean)))
    return graph


if __name__ == "__main__":
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("params", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    graph = build_graph(args.csv, args.params)
    graph.serialize(destination=args.output, format="turtle")
    print(f"{args.output}: {len(graph)} triples")
