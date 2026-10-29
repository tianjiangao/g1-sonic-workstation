#pragma once
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <ifaddrs.h>
#include <unistd.h>
namespace sim_only {
// Hardware joint order, from scene_43dof.xml. Validated against MuJoCo at launch.
inline constexpr float limits[29][2]={
  {-2.5307f,2.8798f},
  {-0.5236f,2.9671f},
  {-2.7576f,2.7576f},
  {-0.087267f,2.8798f},
  {-0.87267f,0.5236f},
  {-0.2618f,0.2618f},
  {-2.5307f,2.8798f},
  {-2.9671f,0.5236f},
  {-2.7576f,2.7576f},
  {-0.087267f,2.8798f},
  {-0.87267f,0.5236f},
  {-0.2618f,0.2618f},
  {-2.618f,2.618f},
  {-0.52f,0.52f},
  {-0.52f,0.52f},
  {-3.0892f,2.6704f},
  {-1.5882f,2.2515f},
  {-2.618f,2.618f},
  {-1.0472f,2.0944f},
  {-1.97222f,1.97222f},
  {-1.61443f,1.61443f},
  {-1.61443f,1.61443f},
  {-3.0892f,2.6704f},
  {-2.2515f,1.5882f},
  {-2.618f,2.618f},
  {-1.0472f,2.0944f},
  {-1.97222f,1.97222f},
  {-1.61443f,1.61443f},
  {-1.61443f,1.61443f}
};
inline float bounded_target(size_t i,float q) {
 if(i>=29 || !std::isfinite(q)) throw std::runtime_error("nonfinite/invalid motor target");
 return std::clamp(q,limits[i][0],limits[i][1]);
}
inline void validate_namespace() {
 char buf[128];auto n=readlink("/proc/self/ns/net",buf,sizeof(buf)-1);
 const char* host=std::getenv("SONIC_HOST_NETNS");
 if(n<=0 || !host) throw std::runtime_error("missing namespace baseline");
 buf[n]=0;if(std::string(buf)==host) throw std::runtime_error("host network forbidden");
 ifaddrs* addrs=nullptr;
 if(getifaddrs(&addrs)) throw std::runtime_error("cannot inspect interfaces");
 bool invalid=false,lo=false;
 for(auto p=addrs;p;p=p->ifa_next){if(std::string(p->ifa_name)!="lo") invalid=true;else lo=true;}
 freeifaddrs(addrs);
 if(invalid || !lo) throw std::runtime_error("only private loopback allowed");
 std::ifstream route("/proc/net/route");std::string line;std::getline(route,line);
 while(std::getline(route,line)) if(line.find_first_not_of(" \t\r\n")!=std::string::npos)
  throw std::runtime_error("IPv4 route forbidden");
 std::cout<<"SIM_ONLY namespace validated; hardware RPC disabled"<<std::endl;
}
}
