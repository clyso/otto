import json
import statistics
import sys
from typing import Tuple, Any
from clyso.ceph.ai.common import jsoncmd


class OSDPerf:
    osd_id: int | None
    perf_dump: dict[str, Any] | None
    onode_hits: int | None
    onode_misses: int | None
    onode_hitrate: float | None

    def __init__(self, osd_id: int | None = None):
        self.osd_id = osd_id
        self.perf_dump = None
        self.onode_hits = None
        self.onode_misses = None
        self.onode_hitrate = None

    def load_from_subprocess(
        self, osd_id: int, skip_confirmation: bool = False
    ) -> None:
        """Load performance data by running subprocess command"""
        self.osd_id = osd_id
        self.perf_dump = self._collect_perf_data_subprocess(skip_confirmation)
        self._extract_onode_metrics()

    def load_from_file(self, file_path: str) -> None:
        """Load performance data from a file"""
        try:
            with open(file_path, "r") as f:
                self.perf_dump = json.load(f)
            self._extract_onode_metrics()
        except FileNotFoundError:
            raise FileNotFoundError(f"Performance data file '{file_path}' not found")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in file '{file_path}': {e}") from e

    def load_from_stdin(self) -> None:
        """Load performance data from stdin"""
        try:
            content = sys.stdin.read()
            self.perf_dump = json.loads(content)
            self._extract_onode_metrics()
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from stdin: {e}") from e

    def load_from_data(self, perf_data: dict[str, Any]) -> None:
        """Load performance data from provided dictionary"""
        self.perf_dump = perf_data
        self._extract_onode_metrics()

    def _collect_perf_data_subprocess(
        self, skip_confirmation: bool = False
    ) -> dict[str, Any]:
        """Collect performance data via subprocess command"""
        if self.osd_id is None:
            raise ValueError("OSD ID must be set for subprocess collection")
        try:
            return jsoncmd(
                f"ceph tell osd.{self.osd_id} perf dump",
                skip_confirmation=skip_confirmation,
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON response from OSD {self.osd_id} perf dump command: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error collecting perf data for OSD {self.osd_id}: {e}"
            ) from e

    def _extract_onode_metrics(self) -> None:
        """Extract onode metrics from loaded performance dump"""
        if not self.perf_dump:
            raise ValueError("No performance data loaded")

        bluestore = self.perf_dump.get("bluestore", {})
        self.onode_hits = bluestore.get("onode_hits", 0)
        self.onode_misses = bluestore.get("onode_misses", 0)

        assert self.onode_hits is not None
        assert self.onode_misses is not None

        self.onode_hitrate = (
            (self.onode_hits / (self.onode_hits + self.onode_misses))
            if (self.onode_hits + self.onode_misses) > 0
            else 0.0
        )

    def get_onode_metrics_json(self) -> str:
        """Get onode metrics as JSON string"""
        if (
            self.onode_hits is None
            or self.onode_misses is None
            or self.onode_hitrate is None
        ):
            raise ValueError("No onode metrics available. Load performance data first.")

        onode_metrics = {
            "onode_hits": self.onode_hits,
            "onode_misses": self.onode_misses,
            "onode_hitrate": self.onode_hitrate,
        }
        return json.dumps(onode_metrics)

    @staticmethod
    def process_perf_dump_file(perf_data: dict[str, Any]) -> list:
        """Process perf dump data from a JSON file and extract OSD metrics"""
        osd_metrics = []

        osd_perf = OSDPerf()
        osd_perf.load_from_data(perf_data)

        osd_metrics.append(
            {
                "osd_id": "unknown",
                "host": "unknown",
                "device_class": "unknown",
                "onode_hits": osd_perf.onode_hits,
                "onode_misses": osd_perf.onode_misses,
                "onode_hitrate": osd_perf.onode_hitrate,
            }
        )

        return osd_metrics

    @classmethod
    def collect_osd_performance_metrics(
        cls, sampled_osds: list, osd_metadata: dict, skip_confirmation: bool = False
    ) -> Tuple[list, list]:
        """Collect onode performance metrics from sampled OSDs"""
        osd_metrics = []
        failed_osds = []

        # Handle bulk confirmation for multiple OSDs
        if not skip_confirmation and len(sampled_osds) > 1:
            osd_list = ", ".join(f"osd.{osd_id}" for osd_id in sorted(sampled_osds))
            try:
                response = (
                    input(
                        f"+ Collect perf dump from {len(sampled_osds)} OSDs ({osd_list}) [y/n]: "
                    )
                    .strip()
                    .lower()
                )
                if response not in ("y", "yes"):
                    print("OSD performance collection cancelled by user.")
                    return [], []
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled by user.")
                return [], []

        skip_confirmation = True

        # TODO: Multi-OSD collection could be parallelized
        # Consider using concurrent.futures.ThreadPoolExecutor for collecting from
        # multiple OSDs simultaneously to reduce overall collection time
        for osd_id in sampled_osds:
            try:
                osd_perf = cls()
                osd_perf.load_from_subprocess(
                    osd_id, skip_confirmation=skip_confirmation
                )
                metadata = osd_metadata[osd_id]

                osd_metrics.append(
                    {
                        "osd_id": osd_id,
                        "host": metadata["host"],
                        "device_class": metadata["device_class"],
                        "onode_hits": osd_perf.onode_hits,
                        "onode_misses": osd_perf.onode_misses,
                        "onode_hitrate": osd_perf.onode_hitrate,
                    }
                )

            except Exception as e:
                failed_osds.append(osd_id)

        return osd_metrics, failed_osds

    @staticmethod
    def collect_from_file_or_stdin(file_path: str | None = None) -> list:
        """Collect performance metrics from file or stdin"""
        osd_perf = OSDPerf()

        if file_path:
            osd_perf.load_from_file(file_path)
        else:
            osd_perf.load_from_stdin()

        return [
            {
                "osd_id": "unknown",
                "host": "unknown",
                "device_class": "unknown",
                "onode_hits": osd_perf.onode_hits,
                "onode_misses": osd_perf.onode_misses,
                "onode_hitrate": osd_perf.onode_hitrate,
            }
        ]

    @staticmethod
    def collect_single_osd_metrics(
        osd_id: int, skip_confirmation: bool = False
    ) -> list:
        """Collect performance metrics from a single OSD"""
        try:
            osd_perf = OSDPerf()
            osd_perf.load_from_subprocess(osd_id, skip_confirmation=skip_confirmation)

            return [
                {
                    "osd_id": osd_id,
                    "host": "unknown",
                    "device_class": "unknown",
                    "onode_hits": osd_perf.onode_hits,
                    "onode_misses": osd_perf.onode_misses,
                    "onode_hitrate": osd_perf.onode_hitrate,
                }
            ]

        except Exception as e:
            raise RuntimeError(
                f"Failed to collect metrics from OSD {osd_id}: {e}"
            ) from e

    @staticmethod
    def analyze_onode_distribution(osd_metrics: list) -> dict:
        """Analyze onode hit rate distribution"""
        if not osd_metrics:
            return {}

        hitrates = [m["onode_hitrate"] for m in osd_metrics]

        analysis = {
            "overall": {
                "count": len(osd_metrics),
                "mean": statistics.mean(hitrates),
                "median": statistics.median(hitrates),
                "min": min(hitrates),
                "max": max(hitrates),
                "std_dev": statistics.stdev(hitrates) if len(hitrates) > 1 else 0.0,
            }
        }

        return analysis


class OSDPerfFormatter:
    """Handles display formatting for OSD performance analysis"""

    @staticmethod
    def format_results(analysis: dict, osd_metrics: list, failed_osds: list) -> str:
        """Format OSD performance analysis results"""
        output = []

        if len(osd_metrics) == 1:
            osd = osd_metrics[0]
            output.append("=" * 40)
            output.append("OSD PERFORMANCE ANALYSIS")
            output.append("=" * 40)
            output.append(f"\nOSD {osd['osd_id']} Onode Metrics:")
            output.append(f"  Hit Rate: {osd['onode_hitrate']:.2%}")
            output.append(f"  Hits:     {osd['onode_hits']:,}")
            output.append(f"  Misses:   {osd['onode_misses']:,}")
            if osd["host"] != "unknown":
                output.append(f"  Host:     {osd['host']}")
            if osd["device_class"] != "unknown":
                output.append(f"  Device:   {osd['device_class']}")
        else:
            output.append("=" * 50)
            output.append("ONODE PERFORMANCE ANALYSIS")
            output.append("=" * 50)

            overall = analysis["overall"]
            output.append(f"\nOnode Hit Rate Distribution:")
            output.append(f"  Sampled OSDs: {overall['count']}")
            output.append(f"  Average: {overall['mean']:.2%}")
            output.append(f"  Median:  {overall['median']:.2%}")
            output.append(f"  Min:     {overall['min']:.2%}")
            output.append(f"  Max:     {overall['max']:.2%}")
            output.append(f"  Std Dev: {overall['std_dev']:.2%}")

            output.append(f"\nIndividual OSD Hit Rate %:")
            sorted_osds = sorted(osd_metrics, key=lambda x: x["onode_hitrate"])
            for osd in sorted_osds:
                host_info = f" ({osd['host']})" if osd["host"] != "unknown" else ""
                output.append(
                    f"  OSD {osd['osd_id']}{host_info}: {osd['onode_hitrate']:.2%}"
                )

        if failed_osds:
            output.append(
                f"\nFailed to collect metrics from OSDs: {sorted(failed_osds)}"
            )

        return "\n".join(output)

    @staticmethod
    def display_results(analysis: dict, osd_metrics: list, failed_osds: list) -> None:
        """Display OSD performance analysis results"""
        print(
            f"\n{OSDPerfFormatter.format_results(analysis, osd_metrics, failed_osds)}"
        )
